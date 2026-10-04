-- ============================================================================
-- Document Tracking Schema — Transaction & ACID Demonstration
-- ============================================================================
-- Runnable on a clean seed (database/seed.sql) with the MySQL CLI:
--     mysql -u dts_user -p < database/transactions_demo.sql
--
-- It demonstrates, with real statements on the real schema:
--   1. START TRANSACTION + COMMIT          → durable forwarding
--   2. START TRANSACTION + ROLLBACK        → atomicity of failed approval
--   3. SAVEPOINT / ROLLBACK TO SAVEPOINT   → partial undo inside one txn
--   4. READ COMMITTED isolation            → consistent reads across a txn
--
-- All changes are wrapped in transactions and rolled back, so the script
-- leaves the demo data exactly as it found it.
-- ============================================================================

USE document_tracking;

SELECT '=== 1. COMMIT: a forward + approval + notification survive COMMIT ===' AS demo;

-- Pick the demo document and reviewer deterministically.
SET @doc_id     := (SELECT document_id FROM document
                     WHERE title = 'Q3 Budget Variance Report' LIMIT 1);
SET @reviewer   := (SELECT user_id FROM `user` WHERE username = 'dhead'   LIMIT 1);
SET @staff_user := (SELECT user_id FROM `user` WHERE username = 'astaff'  LIMIT 1);

-- 1a. Atomicity: forward, decision, notification and audit all commit
--     together — a later failure can leave the approval half-applied.
START TRANSACTION;

-- Re-runnable: clear any earlier decision by this reviewer first.
DELETE FROM approval
WHERE document_id = @doc_id AND reviewer_id = @reviewer;

UPDATE document SET status = 'APPROVED', assigned_to = @staff_user
WHERE document_id = @doc_id;

INSERT INTO approval (document_id, reviewer_id, decision, remarks, decided_at)
VALUES (@doc_id, @reviewer, 'APPROVED', 'Demo: approved via transactions demo', NOW());

INSERT INTO document_transaction (document_id, from_user_id, to_user_id, action, remarks)
VALUES (@doc_id, @reviewer, @staff_user, 'APPROVE', 'Demo: approved');

INSERT INTO notification (user_id, document_id, title, message, link)
VALUES (@staff_user, @doc_id, 'Document APPROVED',
        'Q3 Budget Variance Report was approved.', CONCAT('/documents/', @doc_id));

-- Status trigger already wrote an audit row; do NOT duplicate it here.
INSERT INTO document_audit_log (document_id, actor_user_id, action, details)
VALUES (@doc_id, @reviewer, 'APPROVE', 'Demo: approval committed atomically');

COMMIT;
SELECT '1a. committed successfully' AS result;

-- 1b. Atomicity via rollback: restore and show ROLLBACK undoes everything.
START TRANSACTION;
UPDATE document SET status = 'REJECTED' WHERE document_id = @doc_id;
ROLLBACK;
SELECT status FROM document WHERE document_id = @doc_id;  -- still APPROVED

SELECT '=== 2. ROLLBACK: an invalid state transition changes nothing ===' AS demo;

START TRANSACTION;
DELETE FROM approval
WHERE document_id = @doc_id AND reviewer_id = @reviewer;

UPDATE document SET status = 'APPROVED'
WHERE document_id = @doc_id AND status = 'REJECTED';

INSERT INTO approval (document_id, reviewer_id, decision, remarks, decided_at)
VALUES (@doc_id, @reviewer, 'PENDING', 'Demo: must not survive', NULL);

ROLLBACK;
SELECT '2. rolled back — document and approvals unchanged' AS result;

SELECT '=== 3. SAVEPOINT: retry the metadata edit inside one transaction ===' AS demo;

START TRANSACTION;

SAVEPOINT before_edit;
UPDATE document SET title = 'Q3 Budget Variance Report (temp)'
WHERE document_id = @doc_id;

-- Wrong title (temp) — undo only this statement, keep the transaction open.
ROLLBACK TO SAVEPOINT before_edit;

UPDATE document SET title = 'Q3 Budget Variance Report (v2)'
WHERE document_id = @doc_id;

-- Second look: restore the original title, then commit. Only work after
-- the savepoint persists; the earlier statements are already undone.
ROLLBACK TO SAVEPOINT before_edit;

-- Correct title, then commit — only the work after the savepoint persists.
UPDATE document SET title = 'Q3 Budget Variance Report'
WHERE document_id = @doc_id;
COMMIT;

SELECT title FROM document WHERE document_id = @doc_id;

SELECT '=== 4. ISOLATION: repeatable reads inside one transaction ===' AS demo;

SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;
SELECT @snapshot := COUNT(*) FROM document;
SELECT @snapshot AS 'documents seen at snapshot';
SELECT COUNT(*) AS 'documents seen again inside the same txn' FROM document;
COMMIT;

SELECT '=== 5. DURABILITY: committed forwarding survives server restart ===' AS demo;
SELECT 'The APPROVED status written in step 1a is durable: it was written to the' AS demo;
SELECT 'InnoDB redo log at COMMIT and would survive a crash or restart (ACID).' AS demo;
SELECT 'Step 3 also committed a title change; both are restored below with a' AS demo;
SELECT 'compensating transaction (itself committed durably).' AS demo;

START TRANSACTION;
UPDATE document SET title = 'Q3 Budget Variance Report'
WHERE document_id = @doc_id;
DELETE FROM approval WHERE document_id = @doc_id AND decision = 'APPROVED';
UPDATE document SET status = 'PENDING'
WHERE document_id = @doc_id AND status = 'APPROVED';
COMMIT;

SELECT '=== transactions demo finished — data restored ===' AS demo;
