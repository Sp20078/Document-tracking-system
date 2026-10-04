"""Documents blueprint: CRUD, search/filter, detail, download."""
from flask import (
    Blueprint, current_app, flash, redirect, render_template, request,
    send_file, session, url_for,
)

from .. import db
from ..services.files import delete_upload, resolve_upload_path, save_upload
from ..services.helpers import (
    can_edit_document, can_view_document, is_admin, login_required,
)
from . import forwarding, service

documents_bp = Blueprint("documents", __name__)


def _as_int(raw):
    raw = (raw or "").strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_filters(args) -> dict:
    """Build a filters dict from the query string (whitelisted fields only)."""
    status = (args.get("status") or "").strip().upper()
    priority = (args.get("priority") or "").strip().upper()
    return {
        "q": (args.get("q") or "").strip()[:100] or None,
        "type_id": _as_int(args.get("type_id")),
        "dept_id": _as_int(args.get("dept_id")),
        "status": status if status in service.ALLOWED_STATUSES else None,
        "priority": priority if priority in service.ALLOWED_PRIORITIES else None,
        "creator_id": _as_int(args.get("creator_id")),
        "date_from": (args.get("date_from") or "").strip() or None,
        "date_to": (args.get("date_to") or "").strip() or None,
        "mine": session["user_id"] if args.get("mine") else None,
        "assigned": session["user_id"] if args.get("assigned") else None,
    }


@documents_bp.route("/documents")
@login_required
def index():
    try:
        page = _as_int(request.args.get("page")) or 1
        filters = _parse_filters(request.args)
        rows, meta = service.list_documents(filters, page)
        options = service.get_filter_options()
    except Exception:
        current_app.logger.exception("document list failed")
        return render_template("errors/500.html"), 500
    return render_template("documents/list.html", docs=rows, meta=meta,
                           filters=filters, options=options)


@documents_bp.route("/documents/new", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        form = request.form
        title = (form.get("title") or "").strip()
        description = (form.get("description") or "").strip()
        type_id = _as_int(form.get("document_type_id"))
        dept_id = _as_int(form.get("department_id"))
        priority = (form.get("priority") or "NORMAL").strip().upper()

        # --- server-side validation --------------------------------------
        errors = []
        if len(title) < 3 or len(title) > 200:
            errors.append("Title must be 3-200 characters.")
        if type_id is None or dept_id is None:
            errors.append("Please choose a document type and department.")
        if priority not in service.ALLOWED_PRIORITIES:
            errors.append("Invalid priority.")

        file_path = file_original = None
        upload = request.files.get("attachment")
        if upload and upload.filename:
            try:
                file_path, file_original = save_upload(upload)
            except ValueError as exc:
                errors.append(str(exc))

        if errors:
            for message in errors:
                flash(message, "danger")
            options = service.get_filter_options()
            return render_template("documents/form.html", options=options,
                                   doc=form), 400

        try:
            doc_id = service.create_document(
                title=title, description=description or None,
                type_id=type_id, dept_id=dept_id,
                user_id=session["user_id"], priority=priority,
                file_path=file_path, file_original=file_original)
        except Exception:
            current_app.logger.exception("create document failed")
            if file_path:
                delete_upload(file_path)
            flash("Could not create the document. Please try again.", "danger")
            options = service.get_filter_options()
            return render_template("documents/form.html", options=options,
                                   doc=form), 500

        flash("Document created.", "success")
        return redirect(url_for("documents.detail", document_id=doc_id))

    options = service.get_filter_options()
    return render_template("documents/form.html", options=options, doc=None)


@documents_bp.route("/documents/<int:document_id>")
@login_required
def detail(document_id: int):
    try:
        doc = service.get_document_or_none(document_id)
        if not doc:
            return render_template("errors/404.html"), 404
        if not can_view_document(doc):
            return render_template(
                "errors/403.html",
                message="You do not have access to this document."), 403
        context = {
            "doc": doc,
            "timeline": service.get_timeline(document_id),
            "approvals": service.get_approvals(document_id),
            "comments": service.get_comments(document_id),
            "audit": service.get_audit_trail(document_id),
            "can_edit": can_edit_document(doc),
        }
    except Exception:
        current_app.logger.exception("document detail failed")
        return render_template("errors/500.html"), 500
    return render_template("documents/detail.html", **context)


@documents_bp.route("/documents/<int:document_id>/edit", methods=["GET", "POST"])
@login_required
def edit(document_id: int):
    doc = service.get_document_or_none(document_id)
    if not doc:
        return render_template("errors/404.html"), 404
    if not can_edit_document(doc):
        return render_template(
            "errors/403.html",
            message="You are not allowed to edit this document."), 403

    if request.method == "POST":
        form = request.form
        title = (form.get("title") or "").strip()
        description = (form.get("description") or "").strip()
        priority = (form.get("priority") or "").strip().upper()

        errors = []
        if len(title) < 3 or len(title) > 200:
            errors.append("Title must be 3-200 characters.")
        if priority not in service.ALLOWED_PRIORITIES:
            errors.append("Invalid priority.")

        new_file_path = new_file_original = None
        upload = request.files.get("attachment")
        if upload and upload.filename:
            try:
                new_file_path, new_file_original = save_upload(upload)
            except ValueError as exc:
                errors.append(str(exc))

        if errors:
            for message in errors:
                flash(message, "danger")
                options = service.get_filter_options()
            return render_template("documents/form.html", doc=doc,
                                   options=options), 400

        def work(conn):
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE document
                       SET title = %s, description = %s, priority = %s,
                           file_path = COALESCE(%s, file_path),
                           file_original_name = COALESCE(%s, file_original_name)
                       WHERE document_id = %s""",
                    (title, description or None, priority,
                     new_file_path, new_file_original, document_id))
            service.log_action(conn, session["user_id"], document_id, "EDIT",
                               old_value=doc["title"], new_value=title,
                               details="Document metadata edited")
            return True

        result, error = db.with_transaction(work)
        if result is None:
            if new_file_path:
                delete_upload(new_file_path)
            flash(error or "Could not update the document.", "danger")
            return render_template("documents/form.html", doc=doc,
                                   options=service.get_filter_options()), 500

        if new_file_path and doc.get("file_path"):
            delete_upload(doc["file_path"])  # replaced attachment
        flash("Document updated.", "success")
        return redirect(url_for("documents.detail", document_id=document_id))

    options = service.get_filter_options()
    return render_template("documents/form.html", doc=doc, options=options)


@documents_bp.route("/documents/<int:document_id>/forward", methods=["GET", "POST"])
@login_required
def forward(document_id: int):
    """Forward a document to another user (records history + notification)."""
    doc = service.get_document_or_none(document_id)
    if not doc:
        return render_template("errors/404.html"), 404
    if not (is_admin() or doc.get("created_by") == session["user_id"]
            or doc.get("assigned_to") == session["user_id"]):
        return render_template(
            "errors/403.html",
            message="You are not allowed to forward this document."), 403

    if request.method == "POST":
        to_user_id = _as_int(request.form.get("to_user_id"))
        to_dept_id = _as_int(request.form.get("to_department_id"))
        remarks = (request.form.get("remarks") or "").strip()[:500]
        try:
            forwarding.forward_document(
                document_id, session["user_id"], to_user_id,
                to_department_id=to_dept_id, remarks=remarks)
        except forwarding.ForwardError as exc:
            flash(str(exc), "danger")
        except Exception:
            current_app.logger.exception("forward failed")
            flash("Could not forward the document. Please try again.", "danger")
        else:
            flash("Document forwarded.", "success")
        return redirect(url_for("documents.detail", document_id=document_id))

    users = db.query(
        """SELECT u.user_id, u.full_name, d.name AS department
           FROM `user` u LEFT JOIN department d
             ON d.department_id = u.department_id
           WHERE u.is_active = 1 AND u.user_id <> %s
           ORDER BY u.full_name""",
        (session["user_id"],))
    departments = db.query(
        "SELECT department_id, name FROM department ORDER BY name")
    return render_template("documents/forward.html", doc=doc, users=users,
                           departments=departments)


@documents_bp.route("/documents/<int:document_id>/download")
@login_required
def download(document_id: int):
    doc = service.get_document_or_none(document_id)
    if not doc or not doc.get("file_path"):
        return render_template("errors/404.html"), 404
    if not can_view_document(doc):
        return render_template(
            "errors/403.html",
            message="You do not have access to this attachment."), 403
    try:
        path = resolve_upload_path(doc["file_path"])
    except Exception:
        return render_template("errors/404.html"), 404
    return send_file(path, as_attachment=True,
                     download_name=doc["file_original_name"] or doc["file_path"])
