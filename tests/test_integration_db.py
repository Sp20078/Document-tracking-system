"""Integration tests — REQUIRE a live MySQL server configured in .env.

Run with:  pytest -m integration
They create and drop a dedicated ``document_tracking_test`` database and
never touch the development database. Skipped automatically when MySQL is
unreachable.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import TestingConfig  # noqa: E402

pytestmark = pytest.mark.integration

TEST_DB = TestingConfig.DB_NAME


def _connect(database=None):
    import mysql.connector
    return mysql.connector.connect(
        host=TestingConfig.DB_HOST, port=TestingConfig.DB_PORT,
        user=TestingConfig.DB_USER, password=TestingConfig.DB_PASSWORD,
        database=database, autocommit=False)


@pytest.fixture(scope="module")
def db():
    """Create the test database, load schema+objects+seed, yield, drop."""
    base = _connect()
    with base.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        cur.execute(f"CREATE DATABASE {TEST_DB} CHARACTER SET utf8mb4")
    base.commit()
    base.close()

    conn = _connect(TEST_DB)
    script_dir = os.path.join(os.path.dirname(__file__), "..", "database")
    statements = _load_script(os.path.join(script_dir, "schema.sql"), TEST_DB)
    with conn.cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    # Procedures/functions/triggers need DELIMITER handling: run via CLI-free
    # approach — split on $$ blocks.
    for name in ("views.sql", "procedures.sql", "functions.sql",
                 "triggers.sql", "indexes.sql", "seed.sql"):
        for stmt in _load_script(os.path.join(script_dir, name), TEST_DB):
            with conn.cursor() as cur:
                cur.execute(stmt)
    conn.commit()
    yield conn
    conn.close()

    base = _connect()
    with base.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    base.commit()
    base.close()


def _load_script(path, database):
    """Split a SQL script into executable statements, honoring DELIMITER.

    Pure comment lines and blank lines are skipped BEFORE accumulation so a
    statement preceded by a comment block is not mistaken for a comment.
    """
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    text = text.replace("USE document_tracking;", f"USE {database};")
    text = text.replace("CREATE DATABASE IF NOT EXISTS document_tracking;",
                        f"CREATE DATABASE IF NOT EXISTS {database};")

    statements, buffer = [], []
    delimiter = ";"
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split()[1]
            continue
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(raw_line.rstrip())
        joined = "\n".join(buffer).strip()
        if joined.endswith(delimiter):
            statements.append(joined[: -len(delimiter)].strip())
            buffer = []
    if buffer:
        tail = "\n".join(buffer).strip()
        if tail:
            statements.append(tail)
    return statements


def _one(conn, sql, params=()):
    with conn.cursor(dictionary=True) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _all(conn, sql, params=()):
    with conn.cursor(dictionary=True) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# ---------------------------------------------------------------------------
# schema / seed sanity
# ---------------------------------------------------------------------------

class TestSchemaAndSeed:
    def test_eleven_tables_exist(self, db):
        rows = _all(db, "SHOW TABLES")
        tables = {list(r.values())[0] for r in rows}
        expected = {"department", "role", "document_type", "user",
                    "department_head", "document", "document_transaction",
                    "approval", "comment", "notification", "document_audit_log"}
        assert expected <= tables

    def test_seed_users_created(self, db):
        row = _one(db, "SELECT COUNT(*) AS c FROM `user`")
        assert row["c"] >= 5

    def test_seed_documents_created(self, db):
        row = _one(db, "SELECT COUNT(*) AS c FROM document")
        assert row["c"] >= 5

    def test_every_document_has_history(self, db):
        row = _one(db,
                   "SELECT COUNT(*) AS c FROM document d "
                   "LEFT JOIN document_transaction t ON t.document_id = d.document_id "
                   "WHERE t.transaction_id IS NULL")
        assert row["c"] == 0  # trigger guarantees first transaction row


class TestViews:
    def test_document_overview_view(self, db):
        rows = _all(db, "SELECT * FROM view_document_overview LIMIT 5")
        assert rows and "created_by_name" in rows[0]

    def test_pending_approvals_view(self, db):
        rows = _all(db, "SELECT * FROM view_pending_approvals")
        assert len(rows) == 2  # seeded pending approvals
        assert all("hours_waiting" in r for r in rows)


class TestFunctions:
    def test_count_open_documents(self, db):
        row = _one(db,
                   "SELECT fn_count_open_documents(3, NULL) AS open_docs")
        assert row["open_docs"] >= 2  # astaff's seeded PENDING documents

    def test_unread_notifications(self, db):
        row = _one(db, "SELECT fn_user_unread_notifications(2) AS unread")
        assert row["unread"] >= 1


class TestProceduresAndTriggers:
    def test_sp_create_document_makes_history(self, db):
        before = _one(db, "SELECT COUNT(*) AS c FROM document")["c"]
        with db.cursor() as cur:
            cur.execute(
                "CALL sp_create_document(%s, %s, %s, %s, %s, %s, %s, %s, @new_id)",
                ("Proc Test Doc", "created by procedure", 1, 1, 3, "HIGH",
                 None, None))
            cur.execute("SELECT @_sp_create_document_8 AS new_id")
            new_id = cur.fetchone()[0]
        db.commit()
        after = _one(db, "SELECT COUNT(*) AS c FROM document")["c"]
        assert after == before + 1
        row = _one(db, "SELECT action FROM document_transaction "
                       "WHERE document_id = %s", (new_id,))
        assert row["action"] == "CREATE"  # trigger added the history row

    def test_status_change_writes_single_audit_row(self, db):
        doc = _one(db, "SELECT document_id FROM document "
                       "WHERE status = 'DRAFT' LIMIT 1")
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM document_audit_log "
                        "WHERE document_id = %s", (doc["document_id"],))
            before = cur.fetchone()[0]
            cur.execute(
                "CALL sp_update_document_status(%s, 'PENDING', %s, @ok)",
                (doc["document_id"], 3))
            cur.execute("SELECT @ok AS ok")
            ok = cur.fetchone()[0]
        db.commit()
        assert ok == 1
        with db.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM document_audit_log "
                        "WHERE document_id = %s", (doc["document_id"],))
            after = cur.fetchone()[0]
        assert after == before + 1  # exactly one trigger-written audit row

    def test_invalid_transition_rejected(self, db):
        doc = _one(db, "SELECT document_id FROM document "
                       "WHERE status = 'APPROVED' LIMIT 1")
        with db.cursor() as cur:
            cur.execute(
                "CALL sp_update_document_status(%s, 'PENDING', %s, @ok)",
                (doc["document_id"], 1))
            cur.execute("SELECT @ok AS ok")
            ok = cur.fetchone()[0]
        db.commit()
        assert ok == 0  # APPROVED -> PENDING is not a legal transition

    def test_sp_forward_document_routes_and_notifies(self, db):
        doc = _one(db, "SELECT document_id, assigned_to FROM document "
                       "WHERE status = 'DRAFT' LIMIT 1")
        with db.cursor() as cur:
            cur.execute(
                "CALL sp_forward_document(%s, %s, 4, 2, 'routing test', @ok)",
                (doc["document_id"], doc["assigned_to"]))
            cur.execute("SELECT @ok AS ok")
            ok = cur.fetchone()[0]
        db.commit()
        assert ok == 1
        row = _one(db, "SELECT assigned_to, department_id FROM document "
                       "WHERE document_id = %s", (doc["document_id"],))
        assert row["assigned_to"] == 4 and row["department_id"] == 2
        note = _one(db, "SELECT user_id FROM notification WHERE document_id = %s "
                        "ORDER BY notification_id DESC LIMIT 1",
                    (doc["document_id"],))
        assert note["user_id"] == 4

    def test_forward_unauthorized_actor_rejected(self, db):
        doc = _one(db, "SELECT document_id FROM document "
                       "WHERE status = 'DRAFT' LIMIT 1")
        with db.cursor() as cur:
            cur.execute(
                "CALL sp_forward_document(%s, 4, 3, NULL, NULL, @ok)",
                (doc["document_id"],))
            cur.execute("SELECT @ok AS ok")
            ok = cur.fetchone()[0]
        db.commit()
        assert ok == 0  # user 4 is neither assignee, creator, nor admin


class TestTransactionsAndRollback:
    def test_rollback_undoes_status_and_approval(self, db):
        doc = _one(db, "SELECT document_id, status FROM document "
                       "WHERE status = 'PENDING' LIMIT 1")
        before_status = doc["status"]

        db.start_transaction()
        with db.cursor() as cur:
            cur.execute("UPDATE document SET status = 'REJECTED' "
                        "WHERE document_id = %s", (doc["document_id"],))
            cur.execute("INSERT INTO approval (document_id, reviewer_id, "
                        "decision, remarks, decided_at) "
                        "VALUES (%s, 5, 'REJECTED', 'rollback test', NOW())",
                        (doc["document_id"],))
        db.rollback()

        row = _one(db, "SELECT status FROM document WHERE document_id = %s",
                   (doc["document_id"],))
        assert row["status"] == before_status
        check = _one(db, "SELECT COUNT(*) AS c FROM approval WHERE "
                         "document_id = %s AND remarks = 'rollback test'",
                     (doc["document_id"],))
        assert check["c"] == 0

    def test_savepoint_partial_undo(self, db):
        doc = _one(db, "SELECT document_id FROM document LIMIT 1")
        db.start_transaction()
        with db.cursor() as cur:
            cur.execute("SAVEPOINT sp1")
            cur.execute("UPDATE document SET title = 'Temporary Title' "
                        "WHERE document_id = %s", (doc["document_id"],))
            cur.execute("ROLLBACK TO SAVEPOINT sp1")
            cur.execute("SELECT title FROM document WHERE document_id = %s",
                        (doc["document_id"],))
            title = cur.fetchone()[0]
        db.rollback()
        assert title != "Temporary Title"

    def test_duplicate_approval_blocked_by_unique_key(self, db):
        row = _one(db, "SELECT document_id, reviewer_id FROM approval "
                       "WHERE decision = 'PENDING' LIMIT 1")
        with pytest.raises(Exception):
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO approval (document_id, reviewer_id, decision) "
                    "VALUES (%s, %s, 'APPROVED')",
                    (row["document_id"], row["reviewer_id"]))
        db.rollback()

    def test_orphan_document_prevented_by_fk(self, db):
        with pytest.raises(Exception):
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO document (title, document_type_id, "
                    "department_id, created_by, status) "
                    "VALUES ('Orphan', 1, 9999, 3, 'DRAFT')")
        db.rollback()


class TestIndexes:
    def test_indexes_present(self, db):
        rows = _all(db, "SHOW INDEX FROM document")
        names = {r["Key_name"] for r in rows}
        assert "idx_document_status" in names
        assert "idx_document_created_by" in names
        assert "ft_document_search" in names
