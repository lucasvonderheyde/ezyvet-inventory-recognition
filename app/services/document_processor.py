import shutil
import time
from pathlib import Path

from flask import current_app

from ..models import DocumentRecord, LineItem, db
from .extraction import dump_raw_payload, provider_from_name


class DocumentProcessor:
    def wait_for_stable_file(self, file_path: str) -> bool:
        path = Path(file_path)
        interval = current_app.config["FILE_STABILITY_CHECK_INTERVAL"]
        required_passes = current_app.config["FILE_STABILITY_REQUIRED_PASSES"]
        stable_passes = 0
        previous_size = -1

        while stable_passes < required_passes:
            if not path.exists():
                return False

            current_size = path.stat().st_size
            if current_size == previous_size and current_size > 0:
                stable_passes += 1
            else:
                stable_passes = 0

            previous_size = current_size
            time.sleep(interval)

        return True

    def process_pdf(self, source_path: str) -> DocumentRecord | None:
        path = Path(source_path)
        if not path.exists():
            current_app.logger.warning("Skipping missing file %s", source_path)
            return None

        if not self.wait_for_stable_file(str(path)):
            current_app.logger.warning("File never became stable: %s", source_path)
            return None

        processing_path = self._move_file(path, current_app.config["PROCESSING_FOLDER"])
        record = DocumentRecord(
            original_filename=path.name,
            stored_filename=processing_path.name,
            current_file_path=str(processing_path),
            status="processing",
            extraction_provider=current_app.config["EXTRACTION_PROVIDER"],
        )
        db.session.add(record)
        db.session.commit()

        try:
            payload = provider_from_name(record.extraction_provider).extract(str(processing_path))
            self.apply_extraction_result(record, payload)
            db.session.commit()
            current_app.logger.info("Processed %s into record %s", processing_path.name, record.id)
            return record
        except Exception as exc:
            current_app.logger.exception("Processing failed for %s", processing_path)
            record.status = "error"
            record.extraction_error = str(exc)
            db.session.commit()
            self.move_record_file_for_status(record, "error")
            return record

    def reprocess_record(self, record: DocumentRecord) -> DocumentRecord:
        payload = provider_from_name(record.extraction_provider).extract(record.current_file_path)
        self.apply_extraction_result(record, payload)
        db.session.commit()
        current_app.logger.info("Reprocessed record %s from %s", record.id, record.current_file_path)
        return record

    def apply_extraction_result(self, record: DocumentRecord, payload: dict) -> None:
        record.vendor_name = payload.get("vendor_name")
        record.document_type = payload.get("document_type")
        record.document_number = payload.get("document_number")
        record.document_date = payload.get("document_date")
        record.raw_extraction_json = dump_raw_payload(payload)
        record.status = "pending_review"

        LineItem.query.filter_by(document_id=record.id).delete()

        for index, line_data in enumerate(payload.get("line_items", []), start=1):
            line = LineItem(
                document_id=record.id,
                line_number=index,
                description=line_data.get("description", f"Line {index}"),
                extracted_quantity=self.parse_optional_float(line_data.get("quantity")),
                extracted_unit_price=self.parse_optional_float(line_data.get("unit_price")),
                extracted_line_total=self.parse_optional_float(line_data.get("line_total")),
                actual_quantity_received=self.parse_optional_float(line_data.get("quantity")),
            )
            db.session.add(line)

    def move_record_file_for_status(self, record: DocumentRecord, status: str) -> None:
        destination_root = {
            "ready_for_ezyvet_entry": current_app.config["REVIEWED_FOLDER"],
            "needs_manager_review": current_app.config["REVIEWED_FOLDER"],
            "incomplete": current_app.config["REVIEWED_FOLDER"],
            "error": current_app.config["ERROR_FOLDER"],
        }.get(status)

        if not destination_root:
            return

        current_path = Path(record.current_file_path)
        if not current_path.exists():
            return

        destination_path = self._move_file(current_path, destination_root)
        record.current_file_path = str(destination_path)
        record.stored_filename = destination_path.name
        db.session.commit()

    def _move_file(self, source_path: Path, destination_root: str) -> Path:
        destination_dir = Path(destination_root)
        destination_dir.mkdir(parents=True, exist_ok=True)

        destination_path = destination_dir / source_path.name
        counter = 1
        while destination_path.exists():
            destination_path = destination_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
            counter += 1

        shutil.move(str(source_path), str(destination_path))
        return destination_path

    def parse_optional_float(self, value) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
