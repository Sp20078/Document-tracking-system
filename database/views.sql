-- ============================================================================
-- Document Tracking System — Views
-- ============================================================================
-- view_document_overview
--   Purpose: one joined row per document with human-readable department,
--   type, creator and current holder names, plus derived workflow counters.
--   Used by: document list, dashboard statistics, reports.
--
-- view_pending_approvals
--   Purpose: every open approval task (decision = 'PENDING') joined with
--   document and reviewer details, showing how long it has been waiting.
--   Used by: approval queue and "pending approvals for the logged-in user".
-- ============================================================================
USE document_tracking;

DROP VIEW IF EXISTS view_document_overview;
CREATE VIEW view_document_overview AS
SELECT
  d.document_id,
  d.title,
  d.description,
  dt.name            AS document_type,
  dept.name          AS department_name,
  dept.code          AS department_code,
  u.full_name        AS created_by_name,
  u.username         AS created_by_username,
  a.full_name        AS assigned_to_name,
  d.status,
  d.priority,
  d.file_original_name,
  d.created_at,
  d.updated_at,
  (SELECT COUNT(*) FROM comment c
     WHERE c.document_id = d.document_id)                    AS comment_count,
  (SELECT COUNT(*) FROM approval ap
     WHERE ap.document_id = d.document_id
       AND ap.decision = 'PENDING')                          AS pending_approvals,
  (SELECT COUNT(*) FROM approval ap
     WHERE ap.document_id = d.document_id
       AND ap.decision = 'APPROVED')                         AS approved_count
FROM document d
JOIN document_type dt       ON dt.document_type_id = d.document_type_id
JOIN department dept        ON dept.department_id  = d.department_id
JOIN `user` u               ON u.user_id           = d.created_by
LEFT JOIN `user` a          ON a.user_id           = d.assigned_to;

DROP VIEW IF EXISTS view_pending_approvals;
CREATE VIEW view_pending_approvals AS
SELECT
  ap.approval_id,
  ap.document_id,
  d.title          AS document_title,
  d.priority       AS document_priority,
  d.status         AS document_status,
  dept.name        AS department_name,
  ap.reviewer_id,
  ru.full_name     AS reviewer_name,
  cu.full_name     AS created_by_name,
  ap.created_at    AS requested_at,
  ap.remarks,
  TIMESTAMPDIFF(HOUR, ap.created_at, NOW()) AS hours_waiting
FROM approval ap
JOIN document d  ON d.document_id = ap.document_id
JOIN department dept ON dept.department_id = d.department_id
JOIN `user` ru   ON ru.user_id = ap.reviewer_id
JOIN `user` cu   ON cu.user_id = d.created_by
WHERE ap.decision = 'PENDING';
