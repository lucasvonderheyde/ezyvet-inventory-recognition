from pathlib import Path


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 12 Tf", "50 760 Td"]
    first = True
    for line in lines:
        escaped = escape_pdf_text(line)
        if first:
            content_lines.append(f"({escaped}) Tj")
            first = False
        else:
            content_lines.append("0 -18 Td")
            content_lines.append(f"({escaped}) Tj")
    content_lines.append("ET")
    stream_text = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream_text)).encode("ascii") + b" >>\nstream\n" + stream_text + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    target_dir = base_dir / "storage" / "incoming"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "sample_invoice.pdf"

    lines = [
        "Covetrus Invoice INV-10482",
        "Date 2026-03-26",
        "Canine Rabies Vaccine 10 22.50",
        "Syringe 3mL Luer Lock 50 0.42",
        "Heartworm Test Kit 5 17.80",
    ]
    target_path.write_bytes(build_pdf(lines))
    print(f"Created sample PDF at {target_path}")


if __name__ == "__main__":
    main()
