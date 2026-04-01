import json
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for

from .models import DocumentRecord, db
from .services.document_processor import DocumentProcessor

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def queue():
    status_filter = request.args.get("status", "").strip()
    query = DocumentRecord.query.order_by(DocumentRecord.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)

    records = query.all()
    statuses = [
        "pending_review",
        "ready_for_ezyvet_entry",
        "needs_manager_review",
        "incomplete",
        "error",
    ]
    folder_counts = get_folder_counts()
    error_records = (
        DocumentRecord.query.filter(DocumentRecord.extraction_error.isnot(None))
        .order_by(DocumentRecord.updated_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "queue.html",
        records=records,
        statuses=statuses,
        status_filter=status_filter,
        folder_counts=folder_counts,
        error_records=error_records,
    )


@main_bp.route("/actions/scan-incoming", methods=["POST"])
def scan_incoming():
    processor = DocumentProcessor()
    count = processor.process_incoming_folder()
    flash(f"Scanned Incoming folder. Processed {count} file(s).", "success")
    return redirect(url_for("main.queue"))


@main_bp.route("/actions/recover-processing", methods=["POST"])
def recover_processing():
    processor = DocumentProcessor()
    count = processor.recover_processing_folder()
    flash(f"Recovered {count} file(s) from Processing into the review queue.", "success")
    return redirect(url_for("main.queue"))


@main_bp.route("/records/<int:record_id>", methods=["GET", "POST"])
def review_record(record_id: int):
    record = DocumentRecord.query.get_or_404(record_id)
    extraction_payload = load_extraction_payload(record)

    if request.method == "POST":
        processor = DocumentProcessor()
        for line in record.line_items:
            line.confirmed_correct = request.form.get(f"confirmed_correct_{line.id}") == "on"
            line.item_present = request.form.get(f"item_present_{line.id}") == "on"
            line.actual_quantity_received = processor.parse_optional_float(
                request.form.get(f"actual_quantity_received_{line.id}")
            )
            line.lot_number = request.form.get(f"lot_number_{line.id}", "").strip() or None
            line.expiration_date = request.form.get(f"expiration_date_{line.id}", "").strip() or None
            line.discrepancy_notes = request.form.get(f"discrepancy_notes_{line.id}", "").strip() or None

        new_status = request.form.get("status", record.status)
        record.status = new_status
        record.review_summary = request.form.get("review_summary", "").strip() or None
        record.reviewed_at = datetime.utcnow()
        db.session.commit()

        if new_status in {"ready_for_ezyvet_entry", "needs_manager_review", "incomplete", "error"}:
            processor.move_record_file_for_status(record, new_status)

        flash("Review saved.", "success")
        return redirect(url_for("main.review_record", record_id=record.id))

    return render_template("review.html", record=record, extraction_payload=extraction_payload)


@main_bp.route("/records/<int:record_id>/reprocess", methods=["POST"])
def reprocess_record(record_id: int):
    record = DocumentRecord.query.get_or_404(record_id)
    processor = DocumentProcessor()
    processor.reprocess_record(record)
    flash("Extraction re-ran for this PDF.", "success")
    return redirect(url_for("main.review_record", record_id=record.id))


@main_bp.route("/records/<int:record_id>/pdf")
def view_pdf(record_id: int):
    record = DocumentRecord.query.get_or_404(record_id)
    return send_file(record.current_file_path, mimetype="application/pdf")


def load_extraction_payload(record: DocumentRecord) -> dict:
    if not record.raw_extraction_json:
        return {}

    try:
        return json.loads(record.raw_extraction_json)
    except json.JSONDecodeError:
        return {}


def get_folder_counts() -> dict:
    def count_pdfs(path_value: str) -> int:
        return len(list(Path(path_value).glob("*.pdf")))

    return {
        "incoming": count_pdfs(current_app.config["WATCH_FOLDER"]),
        "processing": count_pdfs(current_app.config["PROCESSING_FOLDER"]),
        "reviewed": count_pdfs(current_app.config["REVIEWED_FOLDER"]),
        "error": count_pdfs(current_app.config["ERROR_FOLDER"]),
    }
