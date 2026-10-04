"""Document forwarding/routing service built on sp_forward_document."""
from .. import db
from ..services.helpers import is_admin


class ForwardError(Exception):
    """Raised with a user-safe message when forwarding is not allowed."""


def forward_document(document_id: int, actor_id: int, to_user_id: int,
                     to_department_id=None, remarks: str = "") -> int:
    """Forward a document to another user, atomically.

    Authorization: current assignee, creator, or administrator.
    Effects (all-or-nothing inside the procedure's transaction):
      * document.assigned_to / department updated
      * document_transaction row (action FORWARD)
      * notification for the recipient
    Returns the recipient user id on success.
    """
    doc = db.query(
        "SELECT document_id, created_by, assigned_to, status "
        "FROM document WHERE document_id = %s", (document_id,), one=True)
    if not doc:
        raise ForwardError("Document not found.")
    if doc["status"] == "APPROVED":
        raise ForwardError(
            "Approved documents can no longer be forwarded.")
    if not (is_admin() or doc["created_by"] == actor_id
            or doc["assigned_to"] == actor_id):
        raise ForwardError("You are not allowed to forward this document.")

    recipient = db.query(
        """SELECT u.user_id, u.department_id, d.name AS dept_name
           FROM `user` u LEFT JOIN department d
             ON d.department_id = u.department_id
           WHERE u.user_id = %s AND u.is_active = 1""",
        (to_user_id,), one=True)
    if not recipient:
        raise ForwardError("Recipient not found or inactive.")

    def work(conn):
        with conn.cursor() as cur:
            cur.execute("CALL sp_forward_document(%s, %s, %s, %s, %s, @out_success)",
                        (document_id, actor_id, to_user_id,
                         to_department_id, remarks or None))
            cur.execute("SELECT @out_success AS ok")
            row = cur.fetchone()
        if not row or not row[0]:
            raise ForwardError("Forwarding was rejected by the database.")
        return to_user_id

    result, error = db.with_transaction(work)
    if result is None:
        raise ForwardError(error or "Forwarding failed.")
    return result
