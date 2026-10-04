"""Notifications blueprint: list, unread badge, mark as read."""
from flask import Blueprint, current_app, flash, redirect, render_template, \
    request, session, url_for

from .. import db
from ..services.helpers import login_required

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/notifications")
@login_required
def index():
    try:
        rows = db.query(
            """SELECT n.notification_id, n.title, n.message, n.link,
                      n.is_read, n.created_at, d.title AS document_title
               FROM notification n
               LEFT JOIN document d ON d.document_id = n.document_id
               WHERE n.user_id = %s
               ORDER BY n.created_at DESC, n.notification_id DESC
               LIMIT 100""",
            (session["user_id"],))
        unread = db.query(
            "SELECT COUNT(*) AS c FROM notification "
            "WHERE user_id = %s AND is_read = 0",
            (session["user_id"],), one=True)["c"]
    except Exception:
        current_app.logger.exception("notifications failed")
        return render_template("errors/500.html"), 500
    return render_template("notifications/index.html", notifications=rows,
                           unread=unread)


@notifications_bp.route("/notifications/<int:notification_id>/read",
                        methods=["POST"])
@login_required
def mark_read(notification_id: int):
    """Mark one notification as read (ownership-checked)."""
    try:
        db.execute(
            "UPDATE notification SET is_read = 1 "
            "WHERE notification_id = %s AND user_id = %s",
            (notification_id, session["user_id"]))
    except Exception:
        current_app.logger.exception("mark-read failed")
        flash("Could not update the notification.", "danger")
    return redirect(url_for("notifications.index"))


@notifications_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    try:
        db.execute(
            "UPDATE notification SET is_read = 1 WHERE user_id = %s "
            "AND is_read = 0",
            (session["user_id"],))
        flash("All notifications marked as read.", "success")
    except Exception:
        current_app.logger.exception("mark-all-read failed")
        flash("Could not update notifications.", "danger")
    return redirect(url_for("notifications.index"))
