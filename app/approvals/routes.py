"""Approvals blueprint: approval queue and decision action."""
from flask import Blueprint, current_app, flash, redirect, render_template, \
    request, session, url_for

from .. import db
from ..documents import service as doc_service
from ..services.helpers import can_approve_document, login_required

approvals_bp = Blueprint("approvals", __name__)


@approvals_bp.route("/approvals")
@login_required
def queue():
    """Pending approval tasks for the current user (and all for admins)."""
    try:
        if session.get("role_name") == "Administrator":
            rows = db.query(
                """SELECT * FROM view_pending_approvals
                   ORDER BY hours_waiting DESC""")
            scope = "all departments"
        else:
            rows = db.query(
                """SELECT * FROM view_pending_approvals
                   WHERE reviewer_id = %s
                   ORDER BY hours_waiting DESC""",
                (session["user_id"],))
            scope = "assigned to you"
        _ = doc_service  # joined names come from the view itself
    except Exception:
        current_app.logger.exception("approval queue failed")
        return render_template("errors/500.html"), 500
    return render_template("approvals/queue.html", approvals=rows, scope=scope)


@approvals_bp.route("/documents/<int:document_id>/decide", methods=["POST"])
@login_required
def decide(document_id: int):
    """Approve / reject / return-for-correction atomically."""
    decision = (request.form.get("decision") or "").strip().upper()
    remarks = (request.form.get("remarks") or "").strip()[:500]
    user_id = session["user_id"]

    if decision not in ("APPROVED", "REJECTED", "RETURNED"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("documents.detail", document_id=document_id))

    doc = doc_service.get_document_or_none(document_id)
    if not doc:
        return render_template("errors/404.html"), 404
    if not can_approve_document(doc):
        return render_template(
            "errors/403.html",
            message="You are not authorized to decide this document."), 403
    if decision == "REJECTED" and not remarks:
        flash("Remarks are required when rejecting a document.", "danger")
        return redirect(url_for("documents.detail", document_id=document_id))

    def work(conn):
        with conn.cursor() as cur:
            # Lock the document row to prevent concurrent double decisions.
            cur.execute(
                "SELECT status, assigned_to FROM document WHERE document_id = %s FOR UPDATE",
                (document_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("missing")
            status = row[0]

            allowed = {"PENDING", "UNDER_REVIEW", "RETURNED"}
            if status not in allowed:
                raise PermissionError("invalid-state")

            # Duplicate-decision guard: the UNIQUE(document, reviewer) key plus
            # an existing non-pending row by this reviewer blocks re-deciding.
            cur.execute(
                """SELECT decision FROM approval
                   WHERE document_id = %s AND reviewer_id = %s""",
                (document_id, user_id))
            existing = cur.fetchone()
            if existing and existing[0] != "PENDING":
                raise PermissionError("already-decided")

            # 1) upsert the approval row
            if existing:
                cur.execute(
                    """UPDATE approval
                       SET decision = %s, remarks = %s, decided_at = NOW()
                       WHERE document_id = %s AND reviewer_id = %s""",
                    (decision, remarks or None, document_id, user_id))
            else:
                cur.execute(
                    """INSERT INTO approval
                       (document_id, reviewer_id, decision, remarks, decided_at)
                       VALUES (%s, %s, %s, %s, NOW())""",
                    (document_id, user_id, decision, remarks or None))

            # 2) document status update — trigger writes the audit row
            cur.execute(
                "UPDATE document SET status = %s WHERE document_id = %s",
                (decision if decision != "RETURNED" else "RETURNED",
                 document_id))
            # decision maps 1:1 to the new status (RETURNED -> RETURNED).

            # 3) transaction history
            doc_service.insert_transaction(
                conn, document_id, user_id, doc["assigned_to"], None,
                decision if decision != "RETURNED" else "RETURN",
                remarks or None)

            # 4) notify the creator of the outcome
            doc_service.notify(
                conn, doc["created_by"], document_id,
                f"Document {decision}",
                f"{doc['title']} was {decision.lower()} by "
                f"{session.get('full_name')}.",
                f"/documents/{document_id}")

            # 5) audit entry for the decision itself (trigger covers status)
            doc_service.log_action(
                conn, user_id, document_id,
                f"{decision}" if decision != "RETURNED" else "RETURN",
                old_value=status, new_value=decision,
                details=f"Review remarks: {remarks or '(none)'}")
        return True

    result, error = db.with_transaction(work)
    if result is None:
        if error and "already" in (error or "").lower():
            flash("You have already made a decision on this document.",
                  "warning")
        else:
            current_app.logger.warning("decide failed: %s", error)
            flash("Could not record the decision. Please try again.", "danger")
        return redirect(url_for("documents.detail", document_id=document_id))

    flash(f"Document {decision.lower()}.", "success")
    return redirect(url_for("documents.detail", document_id=document_id))
