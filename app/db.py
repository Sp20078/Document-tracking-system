"""Thin MySQL connector wrapper used by every route/service.

Conventions
-----------
* Queries are always executed with parameterized SQL (%s placeholders) —
  never string interpolation — to prevent SQL injection.
* autocommit is disabled; multi-step operations use with_transaction() so
  partial writes are impossible (application-level atomicity).
* Errors are converted to short, user-safe messages; SQL text is never
  surfaced to end users.
"""
import mysql.connector
from flask import current_app, g, has_app_context


def get_db():
    """Return a connection (cached on flask.g during requests).

    Outside an app context (scripts, integration tests) a fresh connection
    is returned; the caller owns closing it.
    """
    cfg = current_app.config["CFG"]
    if has_app_context():
        if "db" not in g:
            g.db = mysql.connector.connect(**cfg.db_config())
        return g.db
    return mysql.connector.connect(**cfg.db_config())


def close_db(_exc=None):
    """teardown_appcontext hook: close the per-request connection."""
    db = g.pop("db", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass


def query(sql, params=(), one=False):
    """Run a SELECT with bound parameters; return list[dict] or dict/None."""
    conn = get_db()
    with conn.cursor(dictionary=True) as cur:
        cur.execute(sql, params)
        row = cur.fetchone() if one else cur.fetchall()
    return row


def execute(sql, params=(), return_lastrowid=False):
    """Run one INSERT/UPDATE/DELETE and COMMIT on success.

    Returns the affected rowcount (or lastrowid). Raises on SQL errors so
    callers can flash a safe message; nothing is committed on failure.
    """
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        result = cur.lastrowid if return_lastrowid else cur.rowcount
    conn.commit()
    return result


def commit():
    get_db().commit()


def rollback():
    try:
        get_db().rollback()
    except Exception:
        pass


def with_transaction(work):
    """Run work(conn) inside START TRANSACTION / COMMIT / ROLLBACK.

    On any exception the transaction is rolled back and (None, safe_message)
    is returned; on success (result, None). Demonstrates ACID atomicity:
    every statement in work() is applied together or not at all.
    """
    conn = get_db()
    try:
        conn.start_transaction()
        result = work(conn)
        conn.commit()
        return result, None
    except mysql.connector.Error as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        return None, db_error(exc)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return None, "Unexpected error. The operation was rolled back."


def db_error(exc):
    """Map a connector error to a short, user-safe message (no SQL text)."""
    errno = getattr(exc, "errno", None)
    if errno == 1062:
        return "A record with these details already exists."
    if errno == 1451:
        return "This record is referenced by other records and cannot be removed."
    if errno == 1452:
        return "Related record is missing or invalid."
    if errno == 3819:  # CHECK constraint violation
        return "One of the provided values is not allowed."
    if errno == 1644:  # SIGNAL SQLSTATE '45000'
        return str(exc.msg) if getattr(exc, "msg", None) else "Operation not allowed."
    return "A database error occurred. The operation was rolled back."


def ping():
    """SELECT 1 health probe used by /healthz."""
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        return cur.fetchone() is not None
