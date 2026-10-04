"""Session-token CSRF protection for state-changing requests.

A random token is stored in the Flask session and echoed as a hidden field
in every POST form. before_request rejects unsafe methods whose token is
missing or stale, which blocks cross-site form posts.
"""
import secrets

from flask import abort, request, session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_csrf_token() -> str:
    """Return the session CSRF token, creating it on first use."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def csrf_protect():
    """before_request hook enforcing token validation on unsafe methods."""
    if request.method in SAFE_METHODS:
        return None
    token = session.get("csrf_token")
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or not sent or not secrets.compare_digest(sent, token):
        abort(400, description="Invalid or missing CSRF token.")
    return None
