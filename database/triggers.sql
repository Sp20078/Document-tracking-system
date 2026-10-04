-- ============================================================================
-- Document Tracking System — Triggers
-- ============================================================================
-- trg_document_status (AFTER UPDATE ON document)
--   Purpose: automatic, tamper-resistant audit logging of every status
--   change, plus a notification to the current assignee. Fires regardless of
--   whether the change came from the app, the stored procedure, or a DBA —
--   so the application code must NOT insert a duplicate audit row for the
--   same status change.
--   guards:
--     * only fires when OLD.status <> NEW.status
--     * DATA modification (title/description) is audited by
--       trg_document_update; INSERTs are audited by the app layer because
--       BEFORE/AFTER INSERT triggers cannot know the actor reliably.
--
-- trg_document_update (AFTER UPDATE ON document)
--   Purpose: audit edits to title/description/priority. Kept separate from
--   the status trigger so a row that changes both fields and status produces
--   exactly one audit line per concern, never duplicates.
--
-- trg_document_first_transaction (AFTER INSERT ON document)
--   Purpose: guarantee the invariant "every document has at least one
--   transaction row" even for inserts that bypass sp_create_document
--   (e.g. manual DBA inserts or tests).
-- ============================================================================
USE document_tracking;

DROP TRIGGER IF EXISTS trg_document_status;
DELIMITER $$
CREATE TRIGGER trg_document_status
AFTER UPDATE ON document
FOR EACH ROW
BEGIN
  IF OLD.status <> NEW.status THEN
    INSERT INTO document_audit_log
      (document_id, actor_user_id, action, old_value, new_value, details)
    VALUES
      (NEW.document_id, NEW.assigned_to,
       CONCAT('STATUS_', NEW.status),
       OLD.status, NEW.status,
       CONCAT('Status changed from ', OLD.status, ' to ', NEW.status));

    IF NEW.assigned_to IS NOT NULL THEN
      INSERT INTO notification
        (user_id, document_id, title, message, link)
      VALUES
        (NEW.assigned_to, NEW.document_id,
         CONCAT('Document ', NEW.status),
         CONCAT('"', NEW.title, '" is now ', NEW.status, '.'),
         CONCAT('/documents/', NEW.document_id));
    END IF;
  END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_document_update;
DELIMITER $$
CREATE TRIGGER trg_document_update
AFTER UPDATE ON document
FOR EACH ROW
BEGIN
  IF OLD.title <> NEW.title
     OR NOT (OLD.description <=> NEW.description)
     OR OLD.priority <> NEW.priority THEN
    INSERT INTO document_audit_log
      (document_id, actor_user_id, action, old_value, new_value, details)
    VALUES
      (NEW.document_id, NEW.assigned_to, 'EDIT',
       CONCAT(OLD.title, ' | ', COALESCE(OLD.priority, '')),
       CONCAT(NEW.title, ' | ', COALESCE(NEW.priority, '')),
       'Document metadata edited');
  END IF;
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_document_first_transaction;
DELIMITER $$
CREATE TRIGGER trg_document_first_transaction
AFTER INSERT ON document
FOR EACH ROW
BEGIN
  IF NOT EXISTS (SELECT 1 FROM document_transaction t
                  WHERE t.document_id = NEW.document_id) THEN
    INSERT INTO document_transaction
      (document_id, from_user_id, to_user_id, action, remarks)
    VALUES
      (NEW.document_id, NEW.created_by, NEW.created_by, 'CREATE',
       'Document created');
  END IF;
END$$
DELIMITER ;
