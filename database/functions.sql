-- ============================================================================
-- Document Tracking System — Stored Functions
-- ============================================================================
-- fn_count_open_documents
--   Purpose: count documents created by a user that are still "open"
--   (not yet approved/rejected), optionally restricted to one department.
--   Used by: dashboard ("my open documents") and report sanity checks.
--   Parameters:
--     IN p_user_id      creator user id
--     IN p_department_id NULL = all departments, otherwise filter by dept
--   Returns: INT count of open documents (DRAFT/PENDING/UNDER_REVIEW/RETURNED)
--
-- fn_user_unread_notifications
--   Purpose: number of unread notifications for a user (navbar badge).
--   Parameters:
--     IN p_user_id  recipient user id
--   Returns: INT unread count
--
-- fn_document_awaiting_days
--   Purpose: hours a document has been waiting since it entered its current
--   status (based on the latest transaction/action timestamp). Returns 0 for
--   unknown documents.
--   Parameters:
--     IN p_document_id  document id
--   Returns: INT hours
-- ============================================================================
USE document_tracking;

DROP FUNCTION IF EXISTS fn_count_open_documents;
DELIMITER $$
CREATE FUNCTION fn_count_open_documents (
  p_user_id         INT UNSIGNED,
  p_department_id   INT UNSIGNED
)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
  DECLARE v_count INT DEFAULT 0;
  SELECT COUNT(*) INTO v_count
  FROM document
  WHERE created_by = p_user_id
    AND status IN ('DRAFT','PENDING','UNDER_REVIEW','RETURNED')
    AND (p_department_id IS NULL OR department_id = p_department_id);
  RETURN v_count;
END$$
DELIMITER ;

DROP FUNCTION IF EXISTS fn_user_unread_notifications;
DELIMITER $$
CREATE FUNCTION fn_user_unread_notifications (
  p_user_id INT UNSIGNED
)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
  DECLARE v_count INT DEFAULT 0;
  SELECT COUNT(*) INTO v_count
  FROM notification
  WHERE user_id = p_user_id AND is_read = 0;
  RETURN v_count;
END$$
DELIMITER ;

DROP FUNCTION IF EXISTS fn_document_awaiting_days;
DELIMITER $$
CREATE FUNCTION fn_document_awaiting_days (
  p_document_id INT UNSIGNED
)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
  DECLARE v_hours INT DEFAULT 0;
  SELECT COALESCE(MAX(TIMESTAMPDIFF(HOUR, t.created_at, NOW())), 0)
    INTO v_hours
  FROM document_transaction t
  WHERE t.document_id = p_document_id;
  RETURN v_hours;
END$$
DELIMITER ;
