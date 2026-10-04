"""Auth blueprint: login, logout, profile."""
from flask import (
    Blueprint, flash, redirect, render_template, request, session, url_for,
)

from .. import db
from ..services.helpers import login_required
from . import service

auth_bp = Blueprint("auth", __name__)


def _safe_next(target: str) -> str:
    """Only allow relative, same-site redirect targets."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return ""


def _set_session(user: dict, permanent: bool = False) -> None:
    session.clear()
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["role_name"] = user["role_name"]
    session["department_id"] = user.get("department_id")
    session["department_name"] = user.get("department_name")
    if permanent:
        session.permanent = True


def _audit_login(user_id, username, success: bool) -> None:
    """Audit successful and failed logins without blocking authentication."""
    try:
        db.execute(
            "INSERT INTO document_audit_log (document_id, actor_user_id, action, details) "
            "VALUES (NULL, %s, %s, %s)",
            (user_id, "LOGIN_SUCCESS" if success else "LOGIN_FAILED",
             "User '%s'" % username),
        )
    except Exception:
        pass


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        next_url = _safe_next(request.args.get("next") or
                              request.form.get("next") or "")

        try:
            user = service.authenticate(username, password)
        except Exception:
            flash("Database is unavailable. Please try again later.", "danger")
            return render_template("auth/login.html"), 503

        if user:
            _set_session(user)
            _audit_login(user["user_id"], user["username"], True)
            flash("Welcome back, %s!" % user["full_name"], "success")
            if next_url:
                return redirect(next_url)
            return redirect(url_for("dashboard.index"))

        _audit_login(None, username, False)
        flash("Invalid username or password.", "danger")
        return render_template("auth/login.html"), 401

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


def _session_user_stub() -> dict:
    """Profile card data built from the session (used when re-rendering the
    form after a validation error or when the DB row cannot be read)."""
    return {
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "email": None,
        "role_name": session.get("role_name"),
        "department_name": session.get("department_name"),
    }


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user_id = session["user_id"]

    if request.method == "POST":
        current_password = request.form.get("current_password") or ""
        new_password = request.form.get("new_password") or ""
        confirm = request.form.get("confirm_password") or ""

        try:
            row = db.query(
                "SELECT password_hash FROM `user` WHERE user_id = %s",
                (user_id,), one=True)
        except Exception:
            flash("Database is unavailable. Please try again later.", "danger")
            return render_template("auth/profile.html"), 503

        if not row or not service.verify_password(row["password_hash"],
                                                  current_password):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/profile.html",
                                   user=_session_user_stub()), 400

        if len(new_password) < 8:
            flash("New password must be at least 8 characters.", "danger")
            return render_template("auth/profile.html",
                                   user=_session_user_stub()), 400
        if new_password != confirm:
            flash("New passwords do not match.", "danger")
            return render_template("auth/profile.html",
                                   user=_session_user_stub()), 400

        db.execute(
            "UPDATE `user` SET password_hash = %s WHERE user_id = %s",
            (service.hash_password(new_password), user_id))
        flash("Password updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    try:
        user = service.load_session_user(user_id)
    except Exception:
        user = None
    return render_template("auth/profile.html",
                           user=user or _session_user_stub())
