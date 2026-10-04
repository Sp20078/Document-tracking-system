"""Dashboard blueprint: live statistics from real queries."""
from flask import Blueprint, current_app, render_template
from flask import session as flask_session

from .. import db
from ..services.helpers import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    user_id = flask_session["user_id"]
    is_admin_user = flask_session.get("role_name") == "Administrator"
    dept_id = flask_session.get("department_id")

    try:
        # --- headline counters (real queries, no hardcoded numbers) -------
        stats = {
            "total": db.query("SELECT COUNT(*) AS c FROM document", one=True)["c"],
            "pending": db.query(
                "SELECT COUNT(*) AS c FROM document WHERE status = 'PENDING'",
                one=True)["c"],
            "approved": db.query(
                "SELECT COUNT(*) AS c FROM document WHERE status = 'APPROVED'",
                one=True)["c"],
            "rejected": db.query(
                "SELECT COUNT(*) AS c FROM document WHERE status = 'REJECTED'",
                one=True)["c"],
            "mine": db.query(
                "SELECT COUNT(*) AS c FROM document WHERE created_by = %s",
                (user_id,), one=True)["c"],
            "my_open": db.query(
                "SELECT fn_count_open_documents(%s, NULL) AS c",
                (user_id,), one=True)["c"],
        }

        # --- pending approvals for me / my dept head queue ------------------
        if is_admin_user:
            my_approvals = db.query(
                "SELECT * FROM view_pending_approvals ORDER BY hours_waiting DESC LIMIT 8")
        else:
            my_approvals = db.query(
                """SELECT * FROM view_pending_approvals
                   WHERE reviewer_id = %s ORDER BY hours_waiting DESC LIMIT 8""",
                (user_id,))

        # --- recent activity ------------------------------------------------
        recent_docs = db.query(
            """SELECT d.document_id, d.title, d.status, d.priority, d.created_at,
                      dt.name AS document_type, u.full_name AS creator
               FROM document d
               JOIN document_type dt ON dt.document_type_id = d.document_type_id
               JOIN `user` u ON u.user_id = d.created_by
               ORDER BY d.updated_at DESC LIMIT 6""")

        recent_audit = db.query(
            """SELECT a.action, a.details, a.created_at, d.title,
                      u.full_name AS actor
               FROM document_audit_log a
               LEFT JOIN document d ON d.document_id = a.document_id
               LEFT JOIN `user` u ON u.user_id = a.actor_user_id
               ORDER BY a.created_at DESC LIMIT 8""")

        dept_breakdown = db.query(
            """SELECT dept.name, COUNT(d.document_id) AS total
               FROM department dept
               LEFT JOIN document d ON d.department_id = dept.department_id
               GROUP BY dept.department_id, dept.name
               ORDER BY total DESC""")
    except Exception:
        current_app.logger.exception("dashboard failed")
        return render_template("errors/500.html"), 500

    return render_template("dashboard/index.html", stats=stats,
                           my_approvals=my_approvals, recent_docs=recent_docs,
                           recent_audit=recent_audit,
                           dept_breakdown=dept_breakdown,
                           is_admin=is_admin_user)
