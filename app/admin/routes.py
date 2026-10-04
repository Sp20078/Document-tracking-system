"""Admin blueprint: user and department administration (admins only)."""
from flask import Blueprint, current_app, flash, redirect, render_template, \
    request, session, url_for

from .. import db
from ..auth import service as auth_service
from ..services.helpers import login_required, role_required
from . import service

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/users")
@login_required
@role_required("Administrator")
def users():
    try:
        rows = db.query(
            """SELECT u.user_id, u.username, u.email, u.full_name,
                      u.is_active, u.created_at,
                      r.name AS role_name, d.name AS department_name
               FROM `user` u
               JOIN role r ON r.role_id = u.role_id
               LEFT JOIN department d ON d.department_id = u.department_id
               ORDER BY u.username""")
        roles = db.query("SELECT role_id, name FROM role ORDER BY role_id")
        departments = db.query(
            "SELECT department_id, name FROM department ORDER BY name")
    except Exception:
        current_app.logger.exception("admin users failed")
        return render_template("errors/500.html"), 500
    return render_template("admin/users.html", users=rows, roles=roles,
                           departments=departments)


@admin_bp.route("/admin/users/new", methods=["POST"])
@login_required
@role_required("Administrator")
def create_user():
    username = (request.form.get("username") or "").strip().lower()
    email = (request.form.get("email") or "").strip().lower()
    full_name = (request.form.get("full_name") or "").strip()
    password = request.form.get("password") or ""
    role_id = service._as_int(request.form.get("role_id"))
    department_id = service._as_int(request.form.get("department_id"))

    errors = service.validate_new_user(username, email, full_name, password)
    if errors:
        for message in errors:
            flash(message, "danger")
        return redirect(url_for("admin.users"))

    try:
        db.execute(
            """INSERT INTO `user`
               (username, email, password_hash, full_name, role_id, department_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (username, email, auth_service.hash_password(password), full_name,
             role_id, department_id))
        auth_service.log_admin_action(
            session["user_id"], "USER_CREATE",
            details=f"Created user '{username}' (role {role_id})")
        flash(f"User '{username}' created.", "success")
    except Exception as exc:
        current_app.logger.exception("create user failed")
        flash(db.db_error(exc), "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/admin/users/<int:user_id>/edit", methods=["POST"])
@login_required
@role_required("Administrator")
def edit_user(user_id: int):
    full_name = (request.form.get("full_name") or "").strip()
    role_id = service._as_int(request.form.get("role_id"))
    department_id = service._as_int(request.form.get("department_id"))
    is_active = 1 if request.form.get("is_active") == "on" else 0
    new_password = request.form.get("new_password") or ""

    if not full_name or role_id is None:
        flash("Name and role are required.", "danger")
        return redirect(url_for("admin.users"))

    try:
        # Guards: never deactivate/demote yourself out of the system.
        if user_id == session["user_id"] and (not is_active or role_id != 1):
            flash("You cannot deactivate or demote your own account.", "warning")
            return redirect(url_for("admin.users"))

        sets, params = ["full_name = %s", "role_id = %s",
                        "department_id = %s", "is_active = %s"], [
            full_name, role_id, department_id, is_active]
        if new_password:
            if len(new_password) < 8:
                flash("New password must be at least 8 characters.", "danger")
                return redirect(url_for("admin.users"))
            sets.append("password_hash = %s")
            params.append(auth_service.hash_password(new_password))
        params.append(user_id)
        db.execute(f"UPDATE `user` SET {', '.join(sets)} WHERE user_id = %s",
                   tuple(params))

        auth_service.log_admin_action(
            session["user_id"], "USER_UPDATE",
            details=f"Updated user #{user_id}"
                    + (" (password reset)" if new_password else ""))
        flash("User updated.", "success")
    except Exception as exc:
        current_app.logger.exception("edit user failed")
        flash(db.db_error(exc), "danger")
    return redirect(url_for("admin.users"))


@admin_bp.route("/admin/departments")
@login_required
@role_required("Administrator")
def departments():
    try:
        rows = db.query(
            """SELECT d.department_id, d.name, d.code, d.created_at,
                      u.full_name AS head_name,
                      (SELECT COUNT(*) FROM `user` x
                        WHERE x.department_id = d.department_id) AS member_count
               FROM department d
               LEFT JOIN department_head dh ON dh.department_id = d.department_id
               LEFT JOIN `user` u ON u.user_id = dh.user_id
               ORDER BY d.name""")
        heads = db.query(
            """SELECT u.user_id, u.full_name FROM `user` u
               JOIN role r ON r.role_id = u.role_id
               WHERE r.name = 'Department Head' AND u.is_active = 1
               ORDER BY u.full_name""")
    except Exception:
        current_app.logger.exception("admin departments failed")
        return render_template("errors/500.html"), 500
    return render_template("admin/departments.html", departments=rows,
                           heads=heads)


@admin_bp.route("/admin/departments/new", methods=["POST"])
@login_required
@role_required("Administrator")
def create_department():
    name = (request.form.get("name") or "").strip()
    code = (request.form.get("code") or "").strip().upper()
    head_user_id = service._as_int(request.form.get("head_user_id"))
    if not name or not code:
        flash("Department name and code are required.", "danger")
        return redirect(url_for("admin.departments"))
    try:
        def work(conn):
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO department (name, code) VALUES (%s, %s)",
                    (name, code))
                new_id = cur.lastrowid
                if head_user_id:
                    cur.execute(
                        "INSERT INTO department_head (department_id, user_id) "
                        "VALUES (%s, %s)", (new_id, head_user_id))
            return new_id
        db.with_transaction(work)
        auth_service.log_admin_action(
            session["user_id"], "DEPARTMENT_CREATE",
            details=f"Created department '{name}' ({code})")
        flash(f"Department '{name}' created.", "success")
    except Exception as exc:
        current_app.logger.exception("create department failed")
        flash(db.db_error(exc), "danger")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/admin/departments/<int:department_id>/head", methods=["POST"])
@login_required
@role_required("Administrator")
def set_head(department_id: int):
    head_user_id = service._as_int(request.form.get("head_user_id"))
    if head_user_id is None:
        flash("Choose a user to appoint as head.", "danger")
        return redirect(url_for("admin.departments"))
    try:
        db.execute(
            "UPDATE department_head SET user_id = %s WHERE department_id = %s",
            (head_user_id, department_id))
        auth_service.log_admin_action(
            session["user_id"], "DEPARTMENT_HEAD_SET",
            details=f"Department #{department_id} head set to user #{head_user_id}")
        flash("Department head updated.", "success")
    except Exception as exc:
        current_app.logger.exception("set head failed")
        flash(db.db_error(exc), "danger")
    return redirect(url_for("admin.departments"))
