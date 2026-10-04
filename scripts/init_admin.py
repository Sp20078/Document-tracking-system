#!/usr/bin/env python3
"""Initialize (or reset) the administrator account.

For production-style installs: creates the administrator from environment
variables WITHOUT writing credentials to any committed file.

Required environment variables (put them in .env — git-ignored):
    ADMIN_USERNAME   (default: admin)
    ADMIN_EMAIL      required
    ADMIN_PASSWORD   required (min 8 chars)
    ADMIN_FULL_NAME  (default: System Administrator)

Usage:
    python -m scripts.init_admin            # reads .env automatically
    ADMIN_PASSWORD=... python -m scripts.init_admin
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv  # noqa: E402

from app import create_app  # noqa: E402
from app import db  # noqa: E402
from app.auth.service import hash_password  # noqa: E402


def main() -> int:
    load_dotenv()
    username = os.environ.get("ADMIN_USERNAME", "admin")
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    full_name = os.environ.get("ADMIN_FULL_NAME", "System Administrator")

    if not email or not password:
        print("Error: set ADMIN_EMAIL and ADMIN_PASSWORD (e.g. in .env).")
        return 1
    if len(password) < 8:
        print("Error: ADMIN_PASSWORD must be at least 8 characters.")
        return 1

    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        role = db.query("SELECT role_id FROM role WHERE name = 'Administrator'",
                        one=True)
        if not role:
            print("Error: role table not seeded — run database/seed.sql first.")
            return 1

        existing = db.query("SELECT user_id FROM `user` WHERE username = %s",
                            (username,), one=True)
        password_hash = hash_password(password)
        if existing:
            db.execute(
                "UPDATE `user` SET password_hash = %s, email = %s, "
                "full_name = %s, role_id = %s, is_active = 1 WHERE user_id = %s",
                (password_hash, email, full_name, role["role_id"],
                 existing["user_id"]))
            print(f"Administrator '{username}' password reset (user id "
                  f"{existing['user_id']}).")
        else:
            dept = db.query(
                "SELECT department_id FROM department ORDER BY department_id LIMIT 1",
                one=True)
            db.execute(
                "INSERT INTO `user` "
                "(username, email, password_hash, full_name, role_id, department_id) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (username, email, password_hash, full_name,
                 role["role_id"], dept["department_id"] if dept else None))
            print(f"Administrator '{username}' created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
