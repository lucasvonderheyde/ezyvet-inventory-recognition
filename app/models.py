from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class DocumentRecord(db.Model):
    __tablename__ = "document_records"

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    current_file_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pending_review", index=True)
    vendor_name = db.Column(db.String(255))
    document_type = db.Column(db.String(100))
    document_number = db.Column(db.String(100))
    document_date = db.Column(db.String(50))
    extraction_provider = db.Column(db.String(100))
    raw_extraction_json = db.Column(db.Text)
    extraction_error = db.Column(db.Text)
    review_summary = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    reviewed_at = db.Column(db.DateTime)

    line_items = db.relationship(
        "LineItem",
        backref="document",
        cascade="all, delete-orphan",
        order_by="LineItem.id",
    )


class LineItem(db.Model):
    __tablename__ = "line_items"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("document_records.id"), nullable=False, index=True)
    line_number = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    extracted_quantity = db.Column(db.Float)
    extracted_unit_price = db.Column(db.Float)
    extracted_line_total = db.Column(db.Float)
    confirmed_correct = db.Column(db.Boolean, default=True)
    item_present = db.Column(db.Boolean, default=True)
    actual_quantity_received = db.Column(db.Float)
    lot_number = db.Column(db.String(100))
    expiration_date = db.Column(db.String(50))
    discrepancy_notes = db.Column(db.Text)
