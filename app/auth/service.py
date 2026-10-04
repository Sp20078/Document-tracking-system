"""Authentication service: credential checking and session user loading."""
from werkzeug.security import check_password_hash, generate_password_hash

from .. import db


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash or "", password)


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def authenticate(username: str, password: str):
    """Return the user dict when credentials are valid and account active."""
    user = db.query(
        """SELECT u.user_id, u.username, u.email, u.full_name,
                  u.password_hash, u.role_id, u.department_id,
                  u.is_active, r.name AS role_name, d.name AS department_name
           FROM `user` u
           JOIN role r ON r.role_id = u.role_id
           LEFT JOIN department d ON d.department_id = u.department_id
           WHERE u.username = %s""",
        (username,), one=True)
    if not user or not user.get("is_active"):
        return None
    if not verify_password(user["password_hash"], password):
        return None
    user.pop("password_hash", None)
    return user


def load_session_user(user_id: int):
    """Fetch fresh role/department info for a user (used after login and
    after profile edits that could affect permissions)."""
    return db.query(
        """SELECT u.user_id, u.username, u.email, u.full_name,
                  u.role_id, u.department_id, r.name AS role_name,
                  d.name AS department_name
           FROM `user` u
           JOIN role r ON r.role_id = u.role_id
           LEFT JOIN department d ON d.department_id = u.department_id
           WHERE u.user_id = %s AND u.is_active = 1""",
        (user_id,), one=True)


def log_admin_action(actor_id, action, details=None):
    """Audit administrative actions (user create/update/reset/deactivate)."""
    db.execute(
        """INSERT INTO document_audit_log
           (document_id, actor_user_id, action, details)
           VALUES (NULL, %s, %s, %s)""",
        (actor_id, action, details or ""))
