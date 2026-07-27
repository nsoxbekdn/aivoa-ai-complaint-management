"""Turn the sample .txt complaints into text-layer PDFs, so the upload path can be demoed.

Standard library only — a real PDF generator (reportlab, fpdf2) would be another dependency
for four demo files. This writes the smallest valid PDF that carries a Helvetica text layer,
which is exactly what pypdf reads back.

    python samples/make_sample_pdfs.py

ponytail: single page size, no word wrap beyond a fixed column, no unicode beyond Latin-1.
If the samples ever need tables, images or non-Latin text, swap this for reportlab.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

SAMPLES_DIR = Path(__file__).parent
PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 in PDF points
MARGIN = 56
FONT_SIZE = 10
LINE_HEIGHT = 14
MAX_CHARS_PER_LINE = 88
LINES_PER_PAGE = (PAGE_HEIGHT - 2 * MARGIN) // LINE_HEIGHT


def _escape(line: str) -> str:
    """PDF strings escape backslash and parentheses; drop anything outside Latin-1."""
    line = line.encode("latin-1", "replace").decode("latin-1")
    return line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        lines.extend(textwrap.wrap(paragraph, MAX_CHARS_PER_LINE) or [""])
    return lines


def _content_stream(lines: list[str]) -> bytes:
    parts = [f"BT /F1 {FONT_SIZE} Tf {MARGIN} {PAGE_HEIGHT - MARGIN} Td {LINE_HEIGHT} TL"]
    for line in lines:
        parts.append(f"({_escape(line)}) Tj T*")
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def write_pdf(text: str, destination: Path) -> None:
    pages = [
        _content_stream(chunk)
        for chunk in (
            _wrap(text)[start : start + LINES_PER_PAGE]
            for start in range(0, max(len(_wrap(text)), 1), LINES_PER_PAGE)
        )
    ]

    objects: list[bytes] = []
    page_object_ids = [4 + 2 * index for index in range(len(pages))]

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("latin-1"))
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for index, stream in enumerate(pages):
        content_id = page_object_ids[index] + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    xref_offset = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    ).encode("latin-1")

    destination.write_bytes(bytes(out))


def main() -> None:
    for source in sorted(SAMPLES_DIR.glob("*.txt")):
        destination = source.with_suffix(".pdf")
        write_pdf(source.read_text(encoding="utf-8"), destination)
        print(f"wrote {destination.name}")


if __name__ == "__main__":
    main()
