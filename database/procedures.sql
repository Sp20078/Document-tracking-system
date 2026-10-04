-- ============================================================================
-- Document Tracking System — Stored Procedures
-- ============================================================================
-- sp_create_document
--   Purpose: create a document atomically (single statement, single
--   transaction). The trigger trg_document_first_transaction inserts the
--   mandatory first document_transaction row ('CREATE') in the same
--   statement, so a document can never exist without history, and the app
--   must not insert that row itself (it would be duplicated).
--   Parameters:
--     IN p_title            VARCHAR(200)  document title (required)
--     IN p_description      TEXT          optional description
--     IN p_document_type_id document type lookup id
--     IN p_department_id    owning department id
--     IN p_created_by       creator user id
--     IN p_priority         LOW|NORMAL|HIGH|URGENT
--     IN p_file_path        generated safe filename or NULL
--     IN p_file_original    original filename (display only) or NULL
--     OUT p_document_id     new document id
--
-- sp_update_document_status
--   Purpose: the ONLY supported way to change document status from the app.
--   Validates the transition against a whitelist, then updates the document
--   row. Audit logging and assignee notifications are handled by the
--   trg_document_status trigger, so this procedure must not insert audit
--   rows itself (that would create duplicates).
--   Parameters:
--     IN p_document_id  document to update
--     IN p_new_status   PENDING|UNDER_REVIEW|APPROVED|REJECTED|RETURNED|DRAFT
--     IN p_actor_id     acting user id (must be the current assignee,
--                       the department head of the owning department, or an
--                       administrator)
--     OUT p_success     1 = updated, 0 = rejected (unknown document,
--                       invalid transition, or unauthorized actor)
--
-- sp_forward_document
--   Purpose: atomically forward a document to another user (and optionally
--   department): updates document.assigned_to, records the routing action in
--   document_transaction, and notifies the recipient — all or nothing.
--   Parameters:
--     IN p_document_id      document to forward
--     IN p_actor_id         sender user id (must currently hold the document
--                           or be the creator or an administrator)
--     IN p_to_user_id       recipient user id
--     IN p_to_department_id optional destination department or NULL
--     IN p_remarks          routing remarks or NULL
--     OUT p_success         1 = forwarded, 0 = rejected
-- ============================================================================
USE document_tracking;

DROP PROCEDURE IF EXISTS sp_create_document;
DELIMITER $$
CREATE PROCEDURE sp_create_document (
  IN  p_title            VARCHAR(200),
  IN  p_description      TEXT,
  IN  p_document_type_id INT UNSIGNED,
  IN  p_department_id    INT UNSIGNED,
  IN  p_created_by       INT UNSIGNED,
  IN  p_priority         VARCHAR(10),
  IN  p_file_path        VARCHAR(255),
  IN  p_file_original    VARCHAR(255),
  OUT p_document_id      INT UNSIGNED
)
BEGIN
  -- Atomicity: one statement = one implicit transaction. The first
  -- document_transaction row is added by trg_document_first_transaction.
  INSERT INTO document
    (title, description, document_type_id, department_id, created_by,
     assigned_to, status, priority, file_path, file_original_name)
  VALUES
    (p_title, p_description, p_document_type_id, p_department_id,
     p_created_by, p_created_by, 'DRAFT',
     COALESCE(NULLIF(p_priority, ''), 'NORMAL'),
     p_file_path, p_file_original);

  SET p_document_id = LAST_INSERT_ID();
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS sp_update_document_status;
DELIMITER $$
CREATE PROCEDURE sp_update_document_status (
  IN  p_document_id INT UNSIGNED,
  IN  p_new_status  VARCHAR(20),
  IN  p_actor_id    INT UNSIGNED,
  OUT p_success     TINYINT(1)
)
BEGIN
  DECLARE v_current_status VARCHAR(20);
  DECLARE v_dept_id        INT UNSIGNED;
  DECLARE v_creator        INT UNSIGNED;
  DECLARE v_assignee       INT UNSIGNED;
  DECLARE v_is_authorized  TINYINT(1) DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    SET p_success = 0;
  END;

  SET p_success = 0;

  SELECT status, department_id, created_by, assigned_to
    INTO v_current_status, v_dept_id, v_creator, v_assignee
  FROM document
  WHERE document_id = p_document_id;

  -- Unknown document?
  IF v_current_status IS NULL THEN
    SET p_success = 0;
  ELSE
    -- Authorization: current assignee, department head of the owning
    -- department, or administrator.
    IF p_actor_id = v_assignee
       OR p_actor_id = v_creator
       OR EXISTS (SELECT 1 FROM department_head dh
                   WHERE dh.user_id = p_actor_id
                     AND dh.department_id = v_dept_id)
       OR EXISTS (SELECT 1 FROM `user` u
                   JOIN role r ON r.role_id = u.role_id
                   WHERE u.user_id = p_actor_id
                     AND r.name = 'Administrator') THEN
      SET v_is_authorized = 1;
    END IF;

    -- Consistency: only whitelisted transitions are applied.
    IF v_is_authorized = 1
       AND (
            (v_current_status = 'DRAFT'
              AND p_new_status IN ('PENDING','UNDER_REVIEW'))
         OR (v_current_status = 'PENDING'
              AND p_new_status IN ('UNDER_REVIEW','APPROVED','REJECTED','RETURNED'))
         OR (v_current_status = 'UNDER_REVIEW'
              AND p_new_status IN ('APPROVED','REJECTED','RETURNED'))
         OR (v_current_status IN ('REJECTED','RETURNED')
              AND p_new_status IN ('UNDER_REVIEW','PENDING'))
       ) THEN
      START TRANSACTION;
        UPDATE document
           SET status = p_new_status
         WHERE document_id = p_document_id;
        -- trg_document_status (trigger) writes the audit row and notifies
        -- the assignee here, inside the same transaction.
      COMMIT;
      SET p_success = 1;
    END IF;
  END IF;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS sp_forward_document;
DELIMITER $$
CREATE PROCEDURE sp_forward_document (
  IN  p_document_id      INT UNSIGNED,
  IN  p_actor_id         INT UNSIGNED,
  IN  p_to_user_id       INT UNSIGNED,
  IN  p_to_department_id INT UNSIGNED,
  IN  p_remarks          VARCHAR(500),
  OUT p_success          TINYINT(1)
)
BEGIN
  DECLARE v_status     VARCHAR(20);
  DECLARE v_dept_id    INT UNSIGNED;
  DECLARE v_creator    INT UNSIGNED;
  DECLARE v_assignee   INT UNSIGNED;
  DECLARE v_recipient  VARCHAR(120);
  DECLARE v_title      VARCHAR(200);
  DECLARE v_is_authorized TINYINT(1) DEFAULT 0;
  DECLARE EXIT HANDLER FOR SQLEXCEPTION
  BEGIN
    ROLLBACK;
    SET p_success = 0;
  END;

  SET p_success = 0;

  SELECT status, department_id, created_by, assigned_to
    INTO v_status, v_dept_id, v_creator, v_assignee
  FROM document
  WHERE document_id = p_document_id;

  IF v_status IS NOT NULL THEN
    IF p_actor_id = v_assignee
       OR p_actor_id = v_creator
       OR EXISTS (SELECT 1 FROM `user` u
                   JOIN role r ON r.role_id = u.role_id
                   WHERE u.user_id = p_actor_id
                     AND r.name = 'Administrator') THEN
      SET v_is_authorized = 1;
    END IF;
  END IF;

  IF v_is_authorized = 1 AND p_to_user_id IS NOT NULL THEN
    SELECT full_name INTO v_recipient FROM `user` WHERE user_id = p_to_user_id;
    SELECT title    INTO v_title     FROM document WHERE document_id = p_document_id;

    START TRANSACTION;
      UPDATE document
         SET assigned_to = p_to_user_id,
             department_id = COALESCE(p_to_department_id, department_id)
       WHERE document_id = p_document_id;

      INSERT INTO document_transaction
        (document_id, from_user_id, to_user_id, to_department_id, action, remarks)
      VALUES
        (p_document_id, p_actor_id, p_to_user_id, p_to_department_id,
         'FORWARD', p_remarks);

      INSERT INTO notification
        (user_id, document_id, title, message, link)
      VALUES
        (p_to_user_id, p_document_id,
         'Document forwarded to you',
         CONCAT('You received "', v_title, '" from user #', p_actor_id, '.'),
         CONCAT('/documents/', p_document_id));
    COMMIT;
    SET p_success = 1;
  END IF;
END$$
DELIMITER ;
