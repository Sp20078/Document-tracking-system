#!/usr/bin/env python3
"""Create extra demo documents through the app's own service layer.

This exercises the stored-procedure + trigger path exactly like the web app
does. Optional — database/seed.sql already seeds demo documents.

Usage:
    python -m scripts.seed_demo --count 5
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv  # noqa: E402

from app import create_app  # noqa: E402


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5,
                        help="how many documents to create")
    args = parser.parse_args()

    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        from app.documents import service as doc_service

        users = db_users = None
        from app import db  # noqa: F401  (imported here for clarity)
        from app import db as database

        users = database.query(
            "SELECT user_id, department_id FROM `user` WHERE is_active = 1")
        types = database.query("SELECT document_type_id FROM document_type")
        if not users or not types:
            print("Seed the database first (database/seed.sql).")
            return 1

        titles = ["Budget Review", "Quarterly Report", "Vendor Invoice",
                  "Equipment Purchase", "Policy Update", "Audit Response"]
        random.seed(42)
        created = 0
        for i in range(args.count):
            user = random.choice(users)
            doc_type = random.choice(types)
            title = f"{random.choice(titles)} {i + 1:02d}"
            try:
                doc_service.create_document(
                    title=title,
                    description=f"Demo document {i + 1} created by seed_demo.py.",
                    type_id=doc_type["document_type_id"],
                    dept_id=user["department_id"] or 1,
                    user_id=user["user_id"],
                    priority=random.choice(["LOW", "NORMAL", "HIGH", "URGENT"]))
                created += 1
            except Exception as exc:
                print(f"skip '{title}': {database.db_error(exc)}")
        print(f"Created {created} demo documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
