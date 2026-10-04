-- ============================================================================
-- Document Tracking System — Indexes
-- ============================================================================
-- Purpose-driven secondary indexes (InnoDB creates the clustered PK and the
-- UNIQUE/FK indexes declared in schema.sql automatically).
--
--  idx_document_*      → dashboard counts, list filters, "my documents"
--  idx_transaction_*   → chronological history timeline per document/user
--  idx_approval_*      → approval queue ("pending approvals for user X")
--  idx_notification_*  → unread badge, notifications page
--  idx_audit_*         → audit trail lookups per document/actor
--  idx_comment_*       → comment listing per document
--  Full-text index     → natural-language document search
-- ============================================================================
USE document_tracking;

-- --- document ---------------------------------------------------------------
CREATE INDEX idx_document_status    ON document (status);
CREATE INDEX idx_document_priority  ON document (priority);
CREATE INDEX idx_document_created_by ON document (created_by, status);
CREATE INDEX idx_document_department_status ON document (department_id, status);
CREATE INDEX idx_document_assigned_to ON document (assigned_to, status);
CREATE INDEX idx_document_created_at ON document (created_at);
CREATE FULLTEXT INDEX ft_document_search ON document (title, description);

-- --- document_transaction ----------------------------------------------------
CREATE INDEX idx_transaction_document_time
  ON document_transaction (document_id, created_at);
CREATE INDEX idx_transaction_to_user ON document_transaction (to_user_id);
CREATE INDEX idx_transaction_action  ON document_transaction (action);

-- --- approval ----------------------------------------------------------------
CREATE INDEX idx_approval_reviewer_decision ON approval (reviewer_id, decision);
CREATE INDEX idx_approval_document_decision ON approval (document_id, decision);
CREATE INDEX idx_approval_decided_at ON approval (decided_at);

-- --- notification ------------------------------------------------------------
CREATE INDEX idx_notification_user_read ON notification (user_id, is_read);
CREATE INDEX idx_notification_document  ON notification (document_id);
CREATE INDEX idx_notification_created   ON notification (created_at);

-- --- audit log ---------------------------------------------------------------
CREATE INDEX idx_audit_document_time ON document_audit_log (document_id, created_at);
CREATE INDEX idx_audit_actor_time    ON document_audit_log (actor_user_id, created_at);
CREATE INDEX idx_audit_action        ON document_audit_log (action);

-- --- comment -----------------------------------------------------------------
CREATE INDEX idx_comment_document_time ON comment (document_id, created_at);
