"""Documents service: queries, filters, and shared lookups."""
from .. import db
from ..services.helpers import paginate

PAGE_SIZE = 10

ALLOWED_STATUSES = ("DRAFT", "PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED",
                    "RETURNED")
ALLOWED_PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")


def get_document_or_none(document_id: int):
    """Fetch one document with joined names + the head of its department."""
    return db.query(
        """SELECT d.*, dt.name AS document_type, dept.name AS department_name,
                  cu.full_name AS created_by_name,
                  au.full_name AS assigned_to_name,
                  dh.user_id AS head_user_id
           FROM document d
           JOIN document_type dt ON dt.document_type_id = d.document_type_id
           JOIN department dept  ON dept.department_id = d.department_id
           JOIN `user` cu        ON cu.user_id = d.created_by
           LEFT JOIN `user` au   ON au.user_id = d.assigned_to
           LEFT JOIN department_head dh ON dh.department_id = d.department_id
           WHERE d.document_id = %s""",
        (document_id,), one=True)


def get_document_overview(document_id: int):
    """Read a single document through the required SQL view."""
    return db.query(
        "SELECT * FROM view_document_overview WHERE document_id = %s",
        (document_id,), one=True)


def list_documents(filters: dict, page: int, per_page: int = PAGE_SIZE):
    """Search + filter + paginate documents.

    filters keys: q, type_id, dept_id, status, priority, creator_id,
                  date_from, date_to, mine, assigned
    """
    where = []
    params = []

    if filters.get("q"):
        where.append("(d.title LIKE %s OR d.description LIKE %s)")
        like = "%" + filters["q"] + "%"
        params += [like, like]
    if filters.get("type_id"):
        where.append("d.document_type_id = %s")
        params.append(filters["type_id"])
    if filters.get("dept_id"):
        where.append("d.department_id = %s")
        params.append(filters["dept_id"])
    if filters.get("status"):
        where.append("d.status = %s")
        params.append(filters["status"])
    if filters.get("priority"):
        where.append("d.priority = %s")
        params.append(filters["priority"])
    if filters.get("creator_id"):
        where.append("d.created_by = %s")
        params.append(filters["creator_id"])
    if filters.get("date_from"):
        where.append("DATE(d.created_at) >= %s")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        where.append("DATE(d.created_at) <= %s")
        params.append(filters["date_to"])
    if filters.get("assigned"):
        where.append("d.assigned_to = %s")
        params.append(filters["assigned"])
    if filters.get("mine"):
        where.append("d.created_by = %s")
        params.append(filters["mine"])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base_from = """FROM document d
                   JOIN document_type dt ON dt.document_type_id = d.document_type_id
                   JOIN department dept  ON dept.department_id = d.department_id
                   JOIN `user` cu        ON cu.user_id = d.created_by
                   LEFT JOIN `user` au   ON au.user_id = d.assigned_to"""

    total_row = db.query(
        f"SELECT COUNT(*) AS total {base_from} {where_sql}",
        tuple(params), one=True)
    total = (total_row or {}).get("total", 0) if total_row else 0

    offset = (page - 1) * per_page
    rows = db.query(
        f"""SELECT d.document_id, d.title, d.status, d.priority,
                   d.created_at, d.updated_at, d.file_original_name,
                   dt.name AS document_type, dept.name AS department_name,
                   cu.full_name AS created_by_name,
                   au.full_name AS assigned_to_name
            {base_from} {where_sql}
            ORDER BY d.created_at DESC, d.document_id DESC
            LIMIT %s OFFSET %s""",
        tuple(params) + (per_page, offset))

    meta = paginate(total, rows, page, per_page)
    return rows, meta


def get_timeline(document_id: int):
    """Chronological routing/decision history for a document."""
    return db.query(
        """SELECT t.transaction_id, t.action, t.remarks, t.created_at,
                  fu.full_name AS from_user, tu.full_name AS to_user,
                  td.name AS to_department
           FROM document_transaction t
           LEFT JOIN `user` fu ON fu.user_id = t.from_user_id
           LEFT JOIN `user` tu ON tu.user_id = t.to_user_id
           LEFT JOIN department td ON td.department_id = t.to_department_id
           WHERE t.document_id = %s
           ORDER BY t.created_at, t.transaction_id""",
        (document_id,))


def get_audit_trail(document_id: int):
    """Audit log rows for one document, newest first."""
    return db.query(
        """SELECT a.action, a.old_value, a.new_value, a.details, a.created_at,
                  u.full_name AS actor
           FROM document_audit_log a
           LEFT JOIN `user` u ON u.user_id = a.actor_user_id
           WHERE a.document_id = %s
           ORDER BY a.created_at DESC, a.audit_id DESC""",
        (document_id,))


def get_approvals(document_id: int):
    """Approval rows with reviewer names."""
    return db.query(
        """SELECT a.approval_id, a.decision, a.remarks, a.created_at,
                  a.decided_at, u.full_name AS reviewer_name
           FROM approval a
           JOIN `user` u ON u.user_id = a.reviewer_id
           WHERE a.document_id = %s
           ORDER BY a.created_at""",
        (document_id,))


def get_comments(document_id: int):
    """Comments in chronological order."""
    return db.query(
        """SELECT c.comment_id, c.body, c.created_at, u.full_name AS author
           FROM comment c
           JOIN `user` u ON u.user_id = c.user_id
           WHERE c.document_id = %s
           ORDER BY c.created_at""",
        (document_id,))


def get_filter_options():
    """Dropdown data for the list/search form."""
    return {
        "types": db.query("SELECT document_type_id, name FROM document_type ORDER BY name"),
        "departments": db.query("SELECT department_id, name FROM department ORDER BY name"),
        "statuses": ALLOWED_STATUSES,
        "priorities": ALLOWED_PRIORITIES,
    }


def log_action(conn_or_none, actor_id, document_id, action,
               old_value=None, new_value=None, details=None):
    """Application-side audit for actions NOT covered by triggers.

    Trigger coverage (do not duplicate here): STATUS_* on document update.
    """
    sql = ("INSERT INTO document_audit_log "
           "(document_id, actor_user_id, action, old_value, new_value, details) "
           "VALUES (%s, %s, %s, %s, %s, %s)")
    params = (document_id, actor_id, action, old_value, new_value, details)
    if conn_or_none is not None:
        with conn_or_none.cursor() as cur:
            cur.execute(sql, params)
    else:
        db.execute(sql, params)


def insert_transaction(conn, document_id, from_user_id, to_user_id,
                       to_department_id, action, remarks):
    """Insert a routing/decision transaction inside an open transaction."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO document_transaction
               (document_id, from_user_id, to_user_id, to_department_id,
                action, remarks)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (document_id, from_user_id, to_user_id, to_department_id,
             action, remarks))


def notify(conn, user_id, document_id, title, message, link):
    """Insert a notification inside an open transaction."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO notification
               (user_id, document_id, title, message, link)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, document_id, title, message, link))


def create_document(title, description, type_id, dept_id, user_id, priority,
                    file_path=None, file_original=None):
    """Create a document through the required stored procedure.

    sp_create_document inserts the document row; the trigger
    trg_document_first_transaction adds the mandatory first transaction row
    in the same statement, so the app must not insert it again.
    Returns the new document id.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            result_args = cur.callproc(
                "sp_create_document",
                (title, description, type_id, dept_id, user_id, priority,
                 file_path, file_original, 0))
            # OUT parameter arrives at index 8 after fetch/output binding.
            cur.execute("SELECT @_sp_create_document_8 AS new_id")
            new_id = cur.fetchone()[0]
        conn.commit()
        return int(new_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        close_connection(conn)


def get_connection():
    """Connection accessor used by service-level procedures."""
    from .. import db as db_module
    return db_module.get_db()


def close_connection(conn):
    """Close only connections created outside a request-scoped context."""
    from flask import g, has_app_context
    if not has_app_context():
        conn.close()
