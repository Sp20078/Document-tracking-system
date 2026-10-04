"""Shared helpers: authorization checks, pagination, Jinja context."""
import time
from functools import wraps

from flask import current_app, flash, redirect, render_template, request, session, url_for

from .. import db
from .csrf import get_csrf_token

# Human-friendly labels for enum-ish columns used across templates.
STATUS_LABELS = {
    "DRAFT": "Draft",
    "PENDING": "Pending",
    "UNDER_REVIEW": "Under Review",
    "APPROVED": "Approved",
    "REJECTED": "Rejected",
    "RETURNED": "Returned",
}
PRIORITY_LABELS = {"LOW": "Low", "NORMAL": "Normal", "HIGH": "High", "URGENT": "Urgent"}


def login_required(view):
    """Redirect anonymous users to the login page."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def role_required(*role_names):
    """Allow only logged-in users whose role name is listed."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            if session.get("role_name") not in role_names:
                return render_template(
                    "errors/403.html",
                    message="Your role does not have access to this page."), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def is_admin() -> bool:
    return session.get("role_name") == "Administrator"


def can_edit_document(doc: dict) -> bool:
    """Creator, admins, and the department head of the owning department
    may edit a document that has not reached a final decision."""
    if not doc:
        return False
    if is_admin() or doc.get("created_by") == session.get("user_id"):
        return True
    return doc.get("head_user_id") == session.get("user_id")


def can_approve_document(doc: dict) -> bool:
    """Department head of the owning department, the current assignee, or an
    admin — and only while a decision is still possible."""
    if not doc:
        return False
    if doc.get("status") not in ("PENDING", "UNDER_REVIEW", "RETURNED"):
        return False
    return (is_admin()
            or doc.get("head_user_id") == session.get("user_id")
            or doc.get("assigned_to") == session.get("user_id"))


def can_view_document(doc: dict) -> bool:
    """Anyone in the chain: creator, assignee, approver, same-department
    users, department heads, or admins."""
    if not doc:
        return False
    if is_admin():
        return True
    uid = session.get("user_id")
    if uid in (doc.get("created_by"), doc.get("assigned_to"),
               doc.get("head_user_id")):
        return True
    if session.get("department_id") == doc.get("department_id"):
        return True
    # participants (commented / transacted) may view the history thread
    return bool(db.query(
        """SELECT 1 FROM document_transaction t
           WHERE t.document_id = %s AND (t.from_user_id = %s OR t.to_user_id = %s)
           UNION
           SELECT 1 FROM approval a
           WHERE a.document_id = %s AND a.reviewer_id = %s
           LIMIT 1""",
        (doc["document_id"], uid, uid, doc["document_id"], uid), one=True))


def paginate(total, rows, page, per_page):
    """Return template-ready pagination metadata for a filtered query."""
    pages = max(1, -(-total // per_page))
    page = min(max(1, page), pages)
    return {
        "page": page, "per_page": per_page, "total": total, "pages": pages,
        "has_prev": page > 1, "has_next": page < pages,
        "prev_num": page - 1 if page > 1 else None,
        "next_num": page + 1 if page < pages else None,
    }


def register_context_and_filters(app):
    """Jinja globals/filters shared by all templates."""

    @app.context_processor
    def inject_globals():
        unread = 0
        if session.get("user_id"):
            try:
                row = db.query(
                    "SELECT fn_user_unread_notifications(%s) AS unread",
                    (session["user_id"],), one=True)
                unread = (row or {}).get("unread") or 0
            except Exception:
                unread = 0  # DB down: render the shell, not a 500
        return {
            "csrf_token": get_csrf_token,
            "unread_count": unread,
            "current_user": {
                "user_id": session.get("user_id"),
                "username": session.get("username"),
                "full_name": session.get("full_name"),
                "role_name": session.get("role_name"),
                "department": session.get("department_name"),
            },
            "status_label": lambda s: STATUS_LABELS.get(s, s),
            "priority_label": lambda p: PRIORITY_LABELS.get(p, p),
        }

    @app.template_filter("dtformat")
    def dtformat(value, fmt="%Y-%m-%d %H:%M"):
        if value is None:
            return "—"
        return value.strftime(fmt) if hasattr(value, "strftime") else str(value)

    @app.template_filter("timeago")
    def timeago(value):
        if not hasattr(value, "timestamp"):
            return str(value or "—")
        delta = max(0, int(time.time() - value.timestamp()))
        if delta < 60:
            return "just now"
        if delta < 3600:
            n = delta // 60
            return f"{n} minute{'s' if n != 1 else ''} ago"
        if delta < 86400:
            n = delta // 3600
            return f"{n} hour{'s' if n != 1 else ''} ago"
        n = delta // 86400
        return f"{n} day{'s' if n != 1 else ''} ago"
