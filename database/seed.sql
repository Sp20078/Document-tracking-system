-- ============================================================================
-- Document Tracking System — Seed Data
-- ============================================================================
-- Idempotent reference/lookup data + demo users with REAL Werkzeug password
-- hashes (scrypt). Passwords are documented in the README and .env.example
-- instructions — they are demo credentials for a local sandbox only.
-- Never reuse them outside a classroom/demonstration environment.
--
-- Demo accounts (username / password / role):
--   admin      / Admin@123  / Administrator
--   dhead      / Head@123   / Department Head (Finance, dept head)
--   astaff     / Staff@123  / Staff (Finance)
--   bstaff     / Staff@123  / Staff (HR)
-- ============================================================================
USE document_tracking;

-- ----------------------------------------------------------------------------
-- Lookup data (idempotent via INSERT ... ON DUPLICATE KEY UPDATE)
-- ----------------------------------------------------------------------------
INSERT INTO role (role_id, name, description) VALUES
  (1, 'Administrator',   'Full system access, user and department administration'),
  (2, 'Department Head', 'Approves, rejects and routes documents of their department'),
  (3, 'Staff',           'Creates, forwards and tracks documents')
ON DUPLICATE KEY UPDATE description = VALUES(description);

INSERT INTO document_type (document_type_id, name, description) VALUES
  (1, 'Memo',            'Internal memorandum'),
  (2, 'Report',          'Periodic or special report'),
  (3, 'Invoice',         'Billing and payment documents'),
  (4, 'Purchase Request','Procurement request forms'),
  (5, 'Letter',          'Official correspondence')
ON DUPLICATE KEY UPDATE description = VALUES(description);

INSERT INTO department (department_id, name, code) VALUES
  (1, 'Finance',          'FIN'),
  (2, 'Human Resources',  'HR'),
  (3, 'Information Tech', 'IT'),
  (4, 'Operations',       'OPS')
ON DUPLICATE KEY UPDATE name = VALUES(name);

-- ----------------------------------------------------------------------------
-- Users — INSERT IGNORE keeps stable ids on re-runs; update password hashes
-- only when absent (do not clobber a hash that the admin already changed).
-- ----------------------------------------------------------------------------
INSERT IGNORE INTO `user` (user_id, username, email, password_hash, full_name, role_id, department_id) VALUES
  (1, 'admin',  'admin@example.local',  'scrypt:32768:8:1$8NA56LfCxw5agMZ5$a4cceab7d7de2217dac25fa5809e6ccd9329e01e631a2d759d5f764dcc2647ce8e0e3d5f1ef8b98120539179a7077a05348e5fc59778feaa9b9f982ae115e5a1', 'System Administrator', 1, NULL),
  (2, 'dhead',  'dhead@example.local',  'scrypt:32768:8:1$smWHiUq41lLyQxCb$8ba02f7ebf114342c05fc04282f775a76cdf7c6f10930631f710772e361c5f3dd1b8bc1c80dc3a64721d3f538ac9d798cd66f74c4daa39c74699a44f4f4cc60d', 'Debbie Head',          2, 1),
  (3, 'astaff', 'astaff@example.local', 'scrypt:32768:8:1$qVD6tL1a7nJk0Svk$4875f5fd3018e6dc37e818e7dc82e775f4b9dbbd72738b12ca9fd37da459ea9999ec92b4702ec227e6c51591bd2e92cd52c9e4a8333c84ab8c1efb609b11e0d9', 'Amy Staff',            3, 1),
  (4, 'bstaff', 'bstaff@example.local', 'scrypt:32768:8:1$qVD6tL1a7nJk0Svk$4875f5fd3018e6dc37e818e7dc82e775f4b9dbbd72738b12ca9fd37da459ea9999ec92b4702ec227e6c51591bd2e92cd52c9e4a8333c84ab8c1efb609b11e0d9', 'Ben Staff',            3, 2),
  (5, 'ithead', 'ithead@example.local', 'scrypt:32768:8:1$smWHiUq41lLyQxCb$8ba02f7ebf114342c05fc04282f775a76cdf7c6f10930631f710772e361c5f3dd1b8bc1c80dc3a64721d3f538ac9d798cd66f74c4daa39c74699a44f4f4cc60d', 'Ivan Tech',            2, 3);

-- ----------------------------------------------------------------------------
-- Department heads
-- ----------------------------------------------------------------------------
INSERT IGNORE INTO department_head (department_id, user_id) VALUES
  (1, 2),  -- Debbie Head -> Finance
  (3, 5);  -- Ivan Tech   -> IT

-- ----------------------------------------------------------------------------
-- Demo documents (only when the table is empty, so re-runs never duplicate)
-- ----------------------------------------------------------------------------
INSERT INTO document
  (title, description, document_type_id, department_id, created_by,
   assigned_to, status, priority)
SELECT * FROM (
  SELECT 'Q3 Budget Variance Report' AS title,
         'Analysis of Q3 spending versus the approved budget.' AS description,
         2 AS document_type_id, 1 AS department_id, 3 AS created_by,
         2 AS assigned_to, 'PENDING' AS status, 'HIGH' AS priority
  UNION ALL
  SELECT 'Office Supplies Purchase Request', 'Monthly consumables restock.', 4, 1, 3, 2, 'PENDING', 'NORMAL'
  UNION ALL
  SELECT 'Annual Leave Policy Memo', 'Draft update to the leave policy.', 1, 2, 4, 4, 'DRAFT', 'NORMAL'
  UNION ALL
  SELECT 'Server Maintenance Downtime Notice', 'Planned maintenance window notice.', 1, 3, 5, 5, 'APPROVED', 'LOW'
  UNION ALL
  SELECT 'Courier Contract Renewal', 'Renewal terms for courier services.', 5, 1, 3, 2, 'REJECTED', 'NORMAL'
) AS src
WHERE NOT EXISTS (SELECT 1 FROM document);

-- Approval tasks for the pending demo documents above
INSERT INTO approval (document_id, reviewer_id, decision, remarks)
SELECT d.document_id, 2, 'PENDING', NULL
FROM document d
WHERE d.title IN ('Q3 Budget Variance Report','Office Supplies Purchase Request')
  AND NOT EXISTS (SELECT 1 FROM approval a WHERE a.document_id = d.document_id);

-- ----------------------------------------------------------------------------
-- Demo comments and one unread notification per pending approval
-- ----------------------------------------------------------------------------
INSERT INTO comment (document_id, user_id, body)
SELECT d.document_id, 2, 'Please attach the supporting receipts before review.'
FROM document d
WHERE d.title = 'Office Supplies Purchase Request'
  AND NOT EXISTS (SELECT 1 FROM comment c WHERE c.document_id = d.document_id);

INSERT INTO notification (user_id, document_id, title, message, link)
SELECT 2, d.document_id, 'Document forwarded to you',
       CONCAT('You received "', d.title, '" for approval.'),
       CONCAT('/documents/', d.document_id)
FROM document d
WHERE d.title = 'Q3 Budget Variance Report'
  AND NOT EXISTS (SELECT 1 FROM notification n
                   WHERE n.document_id = d.document_id AND n.user_id = 2);

-- History transactions for the approved/rejected demo documents
INSERT INTO document_transaction (document_id, from_user_id, to_user_id, action, remarks)
SELECT d.document_id, 3, 2, 'FORWARD', 'Submitted for approval'
FROM document d
WHERE d.title = 'Q3 Budget Variance Report'
  AND NOT EXISTS (SELECT 1 FROM document_transaction t
                   WHERE t.document_id = d.document_id AND t.action = 'FORWARD');
