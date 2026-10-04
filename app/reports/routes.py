"""Reports blueprint: counts by department/status/type + CSV export."""
import csv
import io
from collections import defaultdict

from flask import Blueprint, current_app, render_template, Response, session

from .. import db
from ..services.helpers import login_required, role_required

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/reports")
@login_required
@role_required("Administrator", "Department Head")
def index():
    try:
        by_department = db.query(
            """SELECT dept.name AS label,
                      COUNT(d.document_id) AS total,
                      SUM(d.status = 'APPROVED') AS approved,
                      SUM(d.status = 'REJECTED') AS rejected,
                      SUM(d.status IN ('PENDING','UNDER_REVIEW')) AS pending
               FROM department dept
               LEFT JOIN document d ON d.department_id = dept.department_id
               GROUP BY dept.department_id, dept.name
               ORDER BY total DESC""")

        by_status = db.query(
            """SELECT status AS label, COUNT(*) AS total
               FROM document GROUP BY status ORDER BY total DESC""")

        by_type = db.query(
            """SELECT dt.name AS label,
                      COUNT(d.document_id) AS total,
                      SUM(d.status IN ('PENDING','UNDER_REVIEW')) AS pending
               FROM document_type dt
               LEFT JOIN document d ON d.document_type_id = dt.document_type_id
               GROUP BY dt.document_type_id, dt.name
               ORDER BY total DESC""")

        workflow = db.query(
            """SELECT
                 (SELECT COUNT(*) FROM approval WHERE decision = 'PENDING')  AS pending_tasks,
                 (SELECT COUNT(*) FROM approval WHERE decision = 'APPROVED') AS approved_tasks,
                 (SELECT COUNT(*) FROM approval WHERE decision = 'REJECTED') AS rejected_tasks,
                 (SELECT COUNT(*) FROM approval WHERE decision = 'RETURNED') AS returned_tasks,
                 (SELECT COUNT(*) FROM document WHERE status IN ('PENDING','UNDER_REVIEW')) AS docs_in_workflow,
                 (SELECT COUNT(*) FROM document WHERE status IN ('APPROVED','REJECTED')) AS docs_completed""")
    except Exception:
        current_app.logger.exception("reports failed")
        return render_template("errors/500.html"), 500
    workflow_row = workflow[0] if workflow else {}
    return render_template("reports/index.html",
                           by_department=by_department, by_status=by_status,
                           by_type=by_type, workflow=workflow_row)


@reports_bp.route("/reports/export/<kind>")
@login_required
@role_required("Administrator", "Department Head")
def export(kind: str):
    """CSV export of the report tables."""
    queries = {
        "by-department": (
            "SELECT dept.name AS department, d.status, COUNT(*) AS total "
            "FROM document d JOIN department dept "
            "ON dept.department_id = d.department_id "
            "GROUP BY dept.name, d.status ORDER BY dept.name"),
        "by-status": (
            "SELECT status, COUNT(*) AS total FROM document "
            "GROUP BY status ORDER BY total DESC"),
        "by-type": (
            "SELECT dt.name AS document_type, d.status, COUNT(*) AS total "
            "FROM document d JOIN document_type dt "
            "ON dt.document_type_id = d.document_type_id "
            "GROUP BY dt.name, d.status ORDER BY dt.name"),
    }
    if kind not in queries:
        return render_template("errors/404.html"), 404
    try:
        rows = db.query(queries[kind])
    except Exception:
        current_app.logger.exception("report export failed")
        return render_template("errors/500.html"), 500

    buf = io.StringIO()
    writer = csv.writer(buf)
    if rows:
        writer.writerow(list(rows[0].keys()))
        for row in rows:
            writer.writerow([row[k] for k in rows[0].keys()])
    data = buf.getvalue()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition":
                 f"attachment; filename=report_{kind}.csv"})
