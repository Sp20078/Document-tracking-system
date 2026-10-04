"""Unit tests for services that do not require MySQL."""
import io
import os

import pytest

from app.documents import service as doc_service
from app.services import files as files_service
from app.services.helpers import (
    STATUS_LABELS, can_approve_document, can_edit_document, is_admin, paginate,
)


class TestAllowedValues:
    def test_statuses_are_whitelisted(self):
        assert set(doc_service.ALLOWED_STATUSES) == {
            "DRAFT", "PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED", "RETURNED"}

    def test_priorities_are_whitelisted(self):
        assert set(doc_service.ALLOWED_PRIORITIES) == {
            "LOW", "NORMAL", "HIGH", "URGENT"}


class TestFileUploadValidation:
    def test_allowed_extensions(self):
        assert files_service.allowed_file("report.pdf")
        assert files_service.allowed_file("scan.PNG")
        assert files_service.allowed_file("data.csv")
        assert not files_service.allowed_file("malware.exe")
        assert not files_service.allowed_file("script.sh")
        assert not files_service.allowed_file("noextension")

    def test_save_upload_rejects_bad_type(self, app):
        from io import BytesIO
        from werkzeug.datastructures import FileStorage
        bad = FileStorage(stream=BytesIO(b"x"), filename="evil.exe",
                          content_type="application/octet-stream")
        with app.test_request_context():
            with pytest.raises(ValueError):
                files_service.save_upload(bad)

    def test_save_upload_generates_safe_name(self, app):
        from io import BytesIO
        from werkzeug.datastructures import FileStorage
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        good = FileStorage(stream=BytesIO(b"hello"), filename="my report.pdf",
                           content_type="application/pdf")
        with app.test_request_context():
            generated, original = files_service.save_upload(good)
        try:
            assert generated.endswith(".pdf")
            assert generated.startswith("app/static") is False
            assert "/" not in generated and "\\" not in generated
            assert original == "my_report.pdf"  # secure_filename applied
            assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], generated))
        finally:
            os.remove(os.path.join(app.config["UPLOAD_FOLDER"], generated))

    def test_resolve_rejects_traversal(self, app):
        with app.test_request_context():
            import werkzeug.exceptions as wz
            with pytest.raises(wz.NotFound):
                files_service.resolve_upload_path("../../../../etc/passwd")
            with pytest.raises(wz.NotFound):
                files_service.resolve_upload_path("../secret.txt")


class TestAuthorizationHelpers:
    def _doc(self, **overrides):
        doc = {"document_id": 1, "created_by": 3, "assigned_to": 2,
               "head_user_id": 9, "status": "PENDING", "department_id": 1}
        doc.update(overrides)
        return doc

    def test_creator_can_edit(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 3
            session["role_name"] = "Staff"
            assert can_edit_document(self._doc())

    def test_other_staff_cannot_edit(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 4
            session["role_name"] = "Staff"
            assert not can_edit_document(self._doc())

    def test_dept_head_can_edit(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 9
            session["role_name"] = "Department Head"
            assert can_edit_document(self._doc())

    def test_head_can_approve(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 9
            session["role_name"] = "Department Head"
            assert can_approve_document(self._doc())

    def test_cannot_approve_final_state(self, app):
        with app.test_request_context():
            from flask import session
            session["user_id"] = 9
            session["role_name"] = "Department Head"
            assert not can_approve_document(self._doc(status="APPROVED"))

    def test_admin_flag(self, app):
        with app.test_request_context():
            from flask import session
            session["role_name"] = "Administrator"
            assert is_admin()


class TestPagination:
    def test_basic_metadata(self):
        meta = paginate(total=95, rows=[], page=2, per_page=10)
        assert meta["pages"] == 10
        assert meta["has_prev"] and meta["has_next"]
        assert meta["prev_num"] == 1 and meta["next_num"] == 3

    def test_page_clamped(self):
        meta = paginate(total=5, rows=[], page=99, per_page=10)
        assert meta["page"] == 1


class TestLabels:
    def test_status_labels_exist(self):
        assert STATUS_LABELS["UNDER_REVIEW"] == "Under Review"
