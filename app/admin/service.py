"""Admin service helpers (validation used by admin routes)."""


def _as_int(raw):
    try:
        return int((raw or "").strip())
    except (TypeError, ValueError):
        return None


def validate_new_user(username, email, full_name, password):
    """Return a list of human-readable validation errors (empty = valid)."""
    errors = []
    import re
    if not re.fullmatch(r"[a-z0-9_.-]{3,50}", username or ""):
        errors.append(
            "Username must be 3-50 chars: letters, digits, dot, dash, underscore.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""):
        errors.append("A valid email address is required.")
    if not full_name or len(full_name) > 120:
        errors.append("Full name is required (max 120 chars).")
    if len(password or "") < 8:
        errors.append("Password must be at least 8 characters.")
    return errors
