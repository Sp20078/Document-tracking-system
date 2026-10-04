"""Shared pytest fixtures.

Unit tests run WITHOUT any database: the app is created with the testing
config and a fake in-memory DB module is injected where needed. Integration
tests (pytest.mark.integration) require a live MySQL instance configured in
the environment / .env and are skipped automatically when it is unreachable.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.config import TestingConfig  # noqa: E402

TestingConfig.UPLOAD_FOLDER = os.path.join(
    os.path.dirname(__file__), "_test_uploads")


class FakeDB:
    """Minimal offline stand-in for app.db used by route-level unit tests."""

    def __init__(self):
        self.queries = []
        self._rows = {}

    def queue_result(self, fragment, rows):
        self._rows[fragment] = rows

    def query(self, sql, params=(), one=False):
        self.queries.append(sql)
        for fragment, rows in self._rows.items():
            if fragment in sql:
                return (rows[0] if one and rows else list(rows))
        return [] if not one else None

    def execute(self, sql, params=(), return_lastrowid=False):
        self.queries.append(sql)
        return 1

    def commit(self):
        pass

    def rollback(self):
        pass

    def with_transaction(self, work):
        try:
            return work(SimpleNamespace(cursor=lambda: None)), None
        except Exception as exc:  # pragma: no cover
            return None, str(exc)

    def db_error(self, exc):
        return "database error"


@pytest.fixture()
def app(monkeypatch):
    """Flask app in testing mode with the DB stubbed out."""
    app = create_app("testing")
    fake = FakeDB()

    import app.services.helpers as helpers
    import app.notifications.routes as notifications_routes

    monkeypatch.setattr(helpers.db, "query", fake.query)
    monkeypatch.setattr(helpers.db, "execute", fake.execute)

    # The fake needs to be shared by every module that imported `db`
    for module_name in ("app.auth.routes", "app.dashboard.routes",
                        "app.reports.routes", "app.notifications.routes",
                        "app.admin.routes", "app.documents.service",
                        "app.documents.routes", "app.approvals.routes",
                        "app.documents.forwarding"):
        module = sys.modules.get(module_name)
        if module and hasattr(module, "db"):
            monkeypatch.setattr(module.db, "query", fake.query, raising=False)
            monkeypatch.setattr(module.db, "execute", fake.execute, raising=False)

    app.extensions["fake_db"] = fake
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def csrf_token(client):
    """Prime the session and return the CSRF token bound to it."""
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-csrf-token"
    return "test-csrf-token"


@pytest.fixture()
def logged_in_client(client, csrf_token):
    """Client with a Staff session (no DB round-trip: session carries role)."""
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["username"] = "astaff"
        sess["full_name"] = "Amy Staff"
        sess["role_name"] = "Staff"
        sess["department_id"] = 1
        sess["department_name"] = "Finance"
    return client


@pytest.fixture()
def admin_client(client, csrf_token):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "admin"
        sess["full_name"] = "System Administrator"
        sess["role_name"] = "Administrator"
        sess["department_id"] = None
        sess["department_name"] = None
    return client


def mysql_available() -> bool:
    """True when a configured MySQL server accepts a test connection."""
    try:
        import mysql.connector
        from app.config import TestingConfig
        cfg = TestingConfig
        conn = mysql.connector.connect(
            host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER,
            password=cfg.DB_PASSWORD, database=cfg.DB_NAME, connection_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def require_mysql():
    """Skip guard for integration tests."""
    if not mysql_available():
        pytest.skip("MySQL server not available — integration test skipped")
