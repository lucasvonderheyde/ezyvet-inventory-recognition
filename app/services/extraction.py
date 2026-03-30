import hashlib
import json
import re
from abc import ABC, abstractmethod
from pathlib import Path

from pypdf import PdfReader

from .ocr import WindowsOcrService


class ExtractionProvider(ABC):
    @abstractmethod
    def extract(self, pdf_path: str) -> dict:
        raise NotImplementedError


class MockExtractionProvider(ExtractionProvider):
    def extract(self, pdf_path: str) -> dict:
        path = Path(pdf_path)
        text = self._extract_text(path)
        ocr_used = False
        filename = path.stem.lower()
        cleaned_text = self._normalize_text(text)

        if not cleaned_text:
            cleaned_text = self._normalize_text(WindowsOcrService().extract_text_from_pdf(str(path)))
            ocr_used = bool(cleaned_text)

        if not cleaned_text:
            return {
                "vendor_name": None,
                "document_type": "unknown",
                "document_number": None,
                "document_date": None,
                "line_items": [],
                "source_text_preview": "",
                "mock_mode": True,
                "warnings": [
                    "No readable text was found in the PDF.",
                    "This scan appears to be image-only, so extraction needs OCR or a searchable PDF export.",
                ],
                "ocr_used": False,
            }

        vendor = self._pick_vendor(cleaned_text, filename)
        document_type = self._pick_document_type(cleaned_text, filename)
        document_number = self._pick_document_number(cleaned_text, path.stem)
        document_date = self._pick_date(cleaned_text)
        line_items = self._build_line_items(cleaned_text)

        return {
            "vendor_name": vendor,
            "document_type": document_type,
            "document_number": document_number,
            "document_date": document_date,
            "line_items": line_items,
            "source_text_preview": cleaned_text[:2000],
            "mock_mode": True,
            "warnings": [],
            "ocr_used": ocr_used,
        }

    def _extract_text(self, path: Path) -> str:
        try:
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""

    def _normalize_text(self, text: str) -> str:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)

    def _pick_vendor(self, text: str, filename: str) -> str:
        candidates = [
            "Covetrus",
            "MWI Animal Health",
            "Patterson Veterinary",
            "Midmark",
            "VetSource",
        ]
        haystack = f"{text} {filename}".lower()
        for candidate in candidates:
            if candidate.lower() in haystack:
                return candidate

        for line in text.splitlines()[:8]:
            if len(line) > 4 and not re.search(r"\d", line) and "invoice" not in line.lower():
                return line[:120]
        return "Unknown Vendor"

    def _pick_document_type(self, text: str, filename: str) -> str:
        haystack = f"{text}\n{filename}".lower()
        if "packing slip" in haystack or "packing" in haystack:
            return "packing_slip"
        if "invoice" in haystack:
            return "invoice"
        if "receipt" in haystack:
            return "receipt"
        return "unknown"

    def _pick_document_number(self, text: str, fallback: str) -> str:
        patterns = [
            r"(?:invoice|invoice no|invoice #|inv #|inv no)\s*[:#]?\s*([A-Z0-9-]{4,})",
            r"(?:packing slip|packing slip no|packing slip #)\s*[:#]?\s*([A-Z0-9-]{4,})",
            r"(?:receipt|receipt #|receipt no)\s*[:#]?\s*([A-Z0-9-]{4,})",
            r"(?:document|order|po|po #|po no)\s*[:#]?\s*([A-Z0-9-]{4,})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1)
                if candidate.lower() not in {"page", "invoice", "date"}:
                    return candidate

        invoice_lines = text.splitlines()
        for index, line in enumerate(invoice_lines):
            if "invoice" in line.lower():
                for candidate in invoice_lines[index : index + 4]:
                    match = re.search(r"\b(\d{5,}|[A-Z0-9-]{6,})\b", candidate)
                    if match and match.group(1).lower() not in {"invoice", "page", "date"}:
                        return match.group(1)

        for line in text.splitlines()[:10]:
            token_match = re.search(r"\b([A-Z]{2,}-?\d{3,}|[A-Z0-9-]{6,})\b", line)
            if token_match:
                return token_match.group(1)

        digest = hashlib.md5(fallback.encode("utf-8")).hexdigest()[:8].upper()
        return f"UNREAD-{digest}"

    def _pick_date(self, text: str) -> str | None:
        match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})", text)
        if match:
            return self._normalize_date(match.group(1))

        for line in text.splitlines()[:12]:
            if "date" in line.lower():
                match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})", line)
                if match:
                    return self._normalize_date(match.group(1))
        return None

    def _normalize_date(self, value: str) -> str:
        if "/" in value:
            month, day, year = value.split("/")
            if len(year) == 2:
                year = f"20{year}"
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return value

    def _build_line_items(self, text: str) -> list[dict]:
        text_lines = [line.strip() for line in text.splitlines() if line.strip()]
        extracted = []
        for raw_line in text_lines:
            if self._looks_like_header_or_total(raw_line):
                continue

            line_item = self._parse_line_item(raw_line)
            if line_item:
                extracted.append(line_item)

        if extracted:
            return extracted

        return self._fallback_description_lines(text_lines)

    def _looks_like_header_or_total(self, raw_line: str) -> bool:
        normalized = raw_line.lower()
        blocked_terms = [
            "description",
            "item",
            "sku",
            "subtotal",
            "total",
            "tax",
            "balance",
            "ship to",
            "bill to",
        ]
        return any(term in normalized for term in blocked_terms)

    def _parse_line_item(self, raw_line: str) -> dict | None:
        if self._looks_like_bad_description(raw_line):
            return None

        money_values = re.findall(r"\$?\d+(?:,\d{3})*(?:\.\d{2})?", raw_line)
        if len(money_values) < 2:
            return None

        qty_match = re.search(r"\b(\d+(?:\.\d+)?)\b", raw_line)
        if not qty_match:
            return None

        numeric_tail = [self._to_float(value) for value in money_values[-3:]]
        numeric_tail = [value for value in numeric_tail if value is not None]
        if len(numeric_tail) < 2:
            return None

        quantity = self._to_float(qty_match.group(1))
        if quantity is None:
            return None

        unit_price = numeric_tail[-2] if len(numeric_tail) >= 2 else None
        line_total = numeric_tail[-1]
        if unit_price is None:
            return None

        description = raw_line[: qty_match.start()].strip(" -:")
        if len(description) < 3:
            return None

        return {
            "description": description,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        }

    def _fallback_description_lines(self, text_lines: list[str]) -> list[dict]:
        collected = []
        item_section = False
        for raw_line in text_lines:
            lower = raw_line.lower()
            if "item number" in lower:
                item_section = True
                continue
            if "invoice total" in lower or "sub-total" in lower or "tax" in lower:
                break
            if not item_section:
                continue
            if self._looks_like_bad_description(raw_line):
                continue
            if sum(char.isalpha() for char in raw_line) < 8:
                continue

            collected.append(
                {
                    "description": raw_line.strip(),
                    "quantity": None,
                    "unit_price": None,
                    "line_total": None,
                }
            )

        return collected[:12]

    def _looks_like_bad_description(self, raw_line: str) -> bool:
        normalized = raw_line.lower()
        if re.search(r"\b(pa|llc|vmd|tel|fax|p\.o\.|box|invoice|terms|date|ship|cust|dea)\b", normalized):
            return True
        if re.fullmatch(r"[A-Z0-9\-./]+", raw_line):
            return True
        if "," in raw_line and re.search(r"\d", raw_line):
            return True
        if "(" in raw_line and ")" in raw_line:
            return True
        return False

    def _to_float(self, value: str) -> float | None:
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None


def provider_from_name(name: str) -> ExtractionProvider:
    providers = {
        "mock": MockExtractionProvider(),
    }
    return providers.get(name, MockExtractionProvider())


def dump_raw_payload(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
