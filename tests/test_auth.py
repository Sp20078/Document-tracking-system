"""Authentication, route protection and RBAC tests (no database needed).

These tests use a session-stubbed Flask test client; they verify routing,
authorization logic and CSRF enforcement without touching MySQL.
"""
import pytest


class TestLoginFlow:
    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Sign in" in resp.data

    def test_dashboard_redirects_anonymous_to_login(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_documents_redirects_anonymous(self, client):
        resp = client.get("/documents")
        assert resp.status_code == 302

    def test_reports_redirects_anonymous(self, client):
        resp = client.get("/reports")
        assert resp.status_code == 302

    def test_profile_redirects_anonymous(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302

    def test_admin_redirects_anonymous(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 302

    def test_notifications_redirects_anonymous(self, client):
        resp = client.get("/notifications")
        assert resp.status_code == 302


class TestRoleBasedAuthorization:
    def test_staff_cannot_access_admin(self, logged_in_client):
        resp = logged_in_client.get("/admin/users")
        assert resp.status_code == 403

    def test_staff_cannot_access_reports(self, logged_in_client):
        resp = logged_in_client.get("/reports")
        assert resp.status_code == 403

    def test_head_cannot_access_admin(self, client, csrf_token):
        with client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["username"] = "dhead"
            sess["full_name"] = "Debbie Head"
            sess["role_name"] = "Department Head"
            sess["department_id"] = 1
        resp = client.get("/admin/users")
        assert resp.status_code == 403

    def test_head_can_access_reports(self, client, csrf_token):
        with client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["username"] = "dhead"
            sess["full_name"] = "Debbie Head"
            sess["role_name"] = "Department Head"
            sess["department_id"] = 1
        resp = client.get("/reports")
        assert resp.status_code == 200

    def test_admin_accesses_admin_area(self, admin_client):
        resp = admin_client.get("/admin/users")
        assert resp.status_code == 200


class TestCsrfProtection:
    def test_post_without_token_rejected(self, logged_in_client):
        resp = logged_in_client.post("/profile", data={
            "current_password": "x", "new_password": "y", "confirm_password": "y"})
        assert resp.status_code == 400

    def test_logout_requires_token(self, logged_in_client):
        resp = logged_in_client.post("/logout", data={})
        assert resp.status_code == 400

    def test_logout_with_token_succeeds(self, logged_in_client):
        resp = logged_in_client.post(
            "/logout", data={"csrf_token": "test-csrf-token"},
            follow_redirects=True)
        assert resp.status_code == 200

    def test_safe_methods_do_not_need_token(self, logged_in_client):
        assert logged_in_client.get("/documents").status_code == 200


class TestValidation:
    def test_password_change_requires_all_fields(self, logged_in_client):
        resp = logged_in_client.post("/profile", data={
            "csrf_token": "test-csrf-token",
            "current_password": "", "new_password": "", "confirm_password": ""})
        assert resp.status_code in (200, 400)

    def test_unknown_page_returns_404(self, logged_in_client):
        resp = logged_in_client.get("/definitely-not-a-route")
        assert resp.status_code == 404
