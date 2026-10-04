"""Secure file upload/download helpers.

* generated filenames (uuid4) — original name is stored separately for
  display only and never used on disk;
* strict extension whitelist + size limit from config;
* all access is resolved inside UPLOAD_FOLDER, defeating path traversal;
* downloads are always authorization-checked by the route first.
"""
import os
import uuid

from flask import abort, current_app
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg",
                      "jpeg", "txt", "csv"}


def allowed_file(filename: str) -> bool:
    return ("." in filename
            and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS)


def save_upload(file_storage) -> tuple[str, str]:
    """Save an incoming upload; return (generated_name, original_name).

    Raises ValueError for disallowed or empty filenames.
    """
    if file_storage is None or not file_storage.filename:
        raise ValueError("No file provided.")
    original = secure_filename(file_storage.filename)
    if not original or not allowed_file(original):
        raise ValueError(
            "File type not allowed. Allowed: " +
            ", ".join(sorted(ALLOWED_EXTENSIONS)))

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)

    ext = original.rsplit(".", 1)[1].lower()
    generated = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(upload_dir, generated))
    return generated, original


def resolve_upload_path(generated_name: str) -> str:
    """Return the absolute path inside UPLOAD_FOLDER or abort(404).

    Path traversal (../, absolute paths, encoded tricks) can never escape
    the uploads directory because the result is forced to be a direct child
    of the real upload folder.
    """
    safe_name = os.path.basename(generated_name or "")
    if safe_name != generated_name or not safe_name:
        abort(404)
    upload_dir = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    full = os.path.realpath(os.path.join(upload_dir, safe_name))
    if not full.startswith(upload_dir + os.sep):
        abort(404)
    if not os.path.isfile(full):
        abort(404)
    return full


def delete_upload(generated_name: str) -> None:
    """Best-effort delete when a document row is removed/updated."""
    try:
        path = resolve_upload_path(generated_name)
        os.remove(path)
    except Exception:
        pass
