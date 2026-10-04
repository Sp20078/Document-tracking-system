-- ============================================================================
-- Document Tracking System — Database Schema (MySQL 8.0+)
-- ============================================================================
-- Creates the normalized relational schema for the Document Tracking System.
--
-- Design notes
--   * 3NF: every non-key attribute depends on the key, the whole key, and
--     nothing but the key (no repeating groups, no transitive dependencies —
--     e.g. a user's department name is never stored on the document row).
--   * All storage engines are InnoDB so that foreign keys and transactions
--     (ACID) are supported.
--   * fk_* ON DELETE rules prevent orphan records while preserving the audit
--     trail: audit rows and notifications are kept (SET NULL on user), and
--     users can never be deleted while they still own documents
--     (RESTRICT on created_by).
--   * naming convention: snake_case, singular entity names, explicit fk_/uq_/
--     chk_/idx_ prefixes for constraint types.
--
-- Run order: schema.sql -> views.sql -> procedures.sql -> functions.sql ->
--            triggers.sql -> indexes.sql -> seed.sql
-- ============================================================================

CREATE DATABASE IF NOT EXISTS document_tracking
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;
USE document_tracking;

-- Drop in dependency order so the script is repeatable.
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS document_audit_log;
DROP TABLE IF EXISTS notification;
DROP TABLE IF EXISTS comment;
DROP TABLE IF EXISTS approval;
DROP TABLE IF EXISTS document_transaction;
DROP TABLE IF EXISTS document;
DROP TABLE IF EXISTS department_head;
DROP TABLE IF EXISTS `user`;
DROP TABLE IF EXISTS document_type;
DROP TABLE IF EXISTS role;
DROP TABLE IF EXISTS department;
SET FOREIGN_KEY_CHECKS = 1;

-- ----------------------------------------------------------------------------
-- 1. department — organizational units
-- ----------------------------------------------------------------------------
CREATE TABLE department (
  department_id   INT UNSIGNED     NOT NULL AUTO_INCREMENT,
  name            VARCHAR(100)     NOT NULL,
  code            VARCHAR(10)      NOT NULL,
  created_at      TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (department_id),
  UNIQUE KEY uq_department_code (code),
  UNIQUE KEY uq_department_name  (name),
  CONSTRAINT chk_department_code_len CHECK (CHAR_LENGTH(code) BETWEEN 2 AND 10)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 2. role — e.g. Administrator, Department Head, Staff (lookup table)
-- ----------------------------------------------------------------------------
CREATE TABLE role (
  role_id     INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  name        VARCHAR(50)   NOT NULL,
  description VARCHAR(255)  NULL,
  PRIMARY KEY (role_id),
  UNIQUE KEY uq_role_name (name)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 3. document_type — lookup for categories (Memo, Report, Invoice, ...)
-- ----------------------------------------------------------------------------
CREATE TABLE document_type (
  document_type_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  name             VARCHAR(80)  NOT NULL,
  description      VARCHAR(255) NULL,
  PRIMARY KEY (document_type_id),
  UNIQUE KEY uq_document_type_name (name)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 4. user — application accounts (role is reserved in MySQL 8, hence quoting)
-- ----------------------------------------------------------------------------
CREATE TABLE `user` (
  user_id         INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  username        VARCHAR(50)   NOT NULL,
  email           VARCHAR(120)  NOT NULL,
  password_hash   VARCHAR(255)  NOT NULL,
  full_name       VARCHAR(120)  NOT NULL,
  role_id         INT UNSIGNED  NOT NULL,
  department_id   INT UNSIGNED  NULL,
  is_active       TINYINT(1)    NOT NULL DEFAULT 1,
  created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  UNIQUE KEY uq_user_username (username),
  UNIQUE KEY uq_user_email (email),
  CONSTRAINT fk_user_role FOREIGN KEY (role_id)
    REFERENCES role (role_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_user_department FOREIGN KEY (department_id)
    REFERENCES department (department_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT chk_user_email CHECK (email LIKE '%_@_%._%'),
  CONSTRAINT chk_user_active CHECK (is_active IN (0, 1))
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 5. department_head — 1:1 mapping of a user to the department they head
-- ----------------------------------------------------------------------------
CREATE TABLE department_head (
  department_head_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  department_id      INT UNSIGNED NOT NULL,
  user_id            INT UNSIGNED NOT NULL,
  appointed_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (department_head_id),
  UNIQUE KEY uq_dept_head_department (department_id),  -- one head per dept
  UNIQUE KEY uq_dept_head_user (user_id),             -- a user heads one dept
  CONSTRAINT fk_dept_head_department FOREIGN KEY (department_id)
    REFERENCES department (department_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_dept_head_user FOREIGN KEY (user_id)
    REFERENCES `user` (user_id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 6. document — the master record of every tracked document
--    status: DRAFT | PENDING | UNDER_REVIEW | APPROVED | REJECTED | RETURNED
--    priority: LOW | NORMAL | HIGH | URGENT
-- ----------------------------------------------------------------------------
CREATE TABLE document (
  document_id        INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  title              VARCHAR(200)  NOT NULL,
  description        TEXT          NULL,
  document_type_id   INT UNSIGNED  NOT NULL,
  department_id      INT UNSIGNED  NOT NULL,
  created_by         INT UNSIGNED  NOT NULL,
  assigned_to        INT UNSIGNED  NULL COMMENT 'user currently holding the document',
  status             VARCHAR(20)   NOT NULL DEFAULT 'DRAFT',
  priority           VARCHAR(10)   NOT NULL DEFAULT 'NORMAL',
  file_path          VARCHAR(255)  NULL COMMENT 'safe generated filename under uploads/',
  file_original_name VARCHAR(255)  NULL COMMENT 'name shown to users',
  created_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (document_id),
  UNIQUE KEY uq_document_title_created (title, created_by),
  CONSTRAINT fk_document_type FOREIGN KEY (document_type_id)
    REFERENCES document_type (document_type_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_document_department FOREIGN KEY (department_id)
    REFERENCES department (department_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_document_creator FOREIGN KEY (created_by)
    REFERENCES `user` (user_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_document_assignee FOREIGN KEY (assigned_to)
    REFERENCES `user` (user_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT chk_document_status CHECK (status IN
    ('DRAFT','PENDING','UNDER_REVIEW','APPROVED','REJECTED','RETURNED')),
  CONSTRAINT chk_document_priority CHECK (priority IN
    ('LOW','NORMAL','HIGH','URGENT'))
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 7. document_transaction — append-only routing history
--    (who forwarded/created the document, to whom, when, remarks)
-- ----------------------------------------------------------------------------
CREATE TABLE document_transaction (
  transaction_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id      INT UNSIGNED NOT NULL,
  from_user_id     INT UNSIGNED NULL COMMENT 'NULL = document creation',
  to_user_id       INT UNSIGNED NULL COMMENT 'NULL = broadcast / none',
  to_department_id INT UNSIGNED NULL COMMENT 'optional forwarding to a dept',
  action           VARCHAR(30)  NOT NULL COMMENT 'CREATE|FORWARD|APPROVE|REJECT|RETURN|UPDATE',
  remarks          VARCHAR(500) NULL,
  created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (transaction_id),
  CONSTRAINT fk_transaction_document FOREIGN KEY (document_id)
    REFERENCES document (document_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_transaction_from_user FOREIGN KEY (from_user_id)
    REFERENCES `user` (user_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT fk_transaction_to_user FOREIGN KEY (to_user_id)
    REFERENCES `user` (user_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT fk_transaction_to_department FOREIGN KEY (to_department_id)
    REFERENCES department (department_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT chk_transaction_action CHECK (action IN
    ('CREATE','FORWARD','APPROVE','REJECT','RETURN','UPDATE','COMMENT'))
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 8. approval — one decision row per reviewer per document
--    uq_approval_document_reviewer prevents duplicate decisions by the same
--    reviewer for the same document.
-- ----------------------------------------------------------------------------
CREATE TABLE approval (
  approval_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id   INT UNSIGNED NOT NULL,
  reviewer_id   INT UNSIGNED NOT NULL,
  decision      VARCHAR(20)  NOT NULL COMMENT 'PENDING|APPROVED|REJECTED|RETURNED',
  remarks       VARCHAR(500) NULL,
  decided_at    TIMESTAMP    NULL,
  created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (approval_id),
  UNIQUE KEY uq_approval_document_reviewer (document_id, reviewer_id),
  CONSTRAINT fk_approval_document FOREIGN KEY (document_id)
    REFERENCES document (document_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_approval_reviewer FOREIGN KEY (reviewer_id)
    REFERENCES `user` (user_id) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT chk_approval_decision CHECK (decision IN
    ('PENDING','APPROVED','REJECTED','RETURNED')),
  CONSTRAINT chk_approval_decided CHECK (
    (decision = 'PENDING' AND decided_at IS NULL)
    OR (decision <> 'PENDING' AND decided_at IS NOT NULL))
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 9. comment — threaded discussion attached to a document
-- ----------------------------------------------------------------------------
CREATE TABLE comment (
  comment_id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  document_id  INT UNSIGNED NOT NULL,
  user_id      INT UNSIGNED NOT NULL,
  body         TEXT         NOT NULL,
  created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (comment_id),
  CONSTRAINT fk_comment_document FOREIGN KEY (document_id)
    REFERENCES document (document_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_comment_user FOREIGN KEY (user_id)
    REFERENCES `user` (user_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT chk_comment_body CHECK (CHAR_LENGTH(TRIM(body)) > 0)
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 10. notification — in-app notifications (unread counts live in the app)
-- ----------------------------------------------------------------------------
CREATE TABLE notification (
  notification_id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id         INT UNSIGNED NOT NULL COMMENT 'recipient',
  document_id     INT UNSIGNED NULL,
  title           VARCHAR(150) NOT NULL,
  message         VARCHAR(500) NOT NULL,
  link            VARCHAR(255) NULL COMMENT 'in-app URL for the notification',
  is_read         TINYINT(1)   NOT NULL DEFAULT 0,
  created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (notification_id),
  CONSTRAINT fk_notification_user FOREIGN KEY (user_id)
    REFERENCES `user` (user_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_notification_document FOREIGN KEY (document_id)
    REFERENCES document (document_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT chk_notification_read CHECK (is_read IN (0, 1))
) ENGINE=InnoDB;

-- ----------------------------------------------------------------------------
-- 11. document_audit_log — tamper-evident history of important actions.
--     Append-only: the app never UPDATEs or DELETEs rows here. The status
--     trigger (trg_document_status) writes rows automatically.
-- ----------------------------------------------------------------------------
CREATE TABLE document_audit_log (
  audit_id      INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  document_id   INT UNSIGNED  NULL,
  actor_user_id INT UNSIGNED  NULL,
  action        VARCHAR(60)   NOT NULL,
  old_value     VARCHAR(500)  NULL,
  new_value     VARCHAR(500)  NULL,
  details       VARCHAR(1000) NULL,
  created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (audit_id),
  CONSTRAINT fk_audit_document FOREIGN KEY (document_id)
    REFERENCES document (document_id) ON DELETE SET NULL ON UPDATE CASCADE,
  CONSTRAINT fk_audit_actor FOREIGN KEY (actor_user_id)
    REFERENCES `user` (user_id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;
