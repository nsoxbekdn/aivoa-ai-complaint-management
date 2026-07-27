"""Generate a fictional image-only complaint for the Groq Vision OCR demonstration."""

from __future__ import annotations

from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
OUTPUT_PDF = HERE / "05_scanned_leaking_bottle.pdf"
OUTPUT_JPG = HERE / "05_scanned_leaking_bottle.jpg"


def build() -> None:
    source = pymupdf.open()
    page = source.new_page(width=595, height=842)
    page.insert_text((52, 62), "MERIDIAN PHARMACY GROUP", fontsize=15, color=(0.13, 0.27, 0.58))
    page.draw_line((52, 75), (543, 75), color=(0.13, 0.27, 0.58), width=2)
    page.insert_text((52, 112), "Customer Product Complaint", fontsize=22)
    page.insert_text((52, 138), "Email received: 25 July 2026", fontsize=10, color=(0.3, 0.3, 0.3))

    facts = [
        ("Reporter", "Meridian Pharmacy Group"),
        ("Contact", "quality@meridianpharmacy.example"),
        ("Product", "ClearCough Syrup 100 ml"),
        ("Strength", "5 mg/5 ml"),
        ("Batch / lot", "CC26045"),
        ("Manufacturing date", "10 April 2025"),
        ("Expiry date", "09 April 2027"),
        ("Quantity affected", "5 bottles"),
        ("Date observed", "25 July 2026"),
    ]
    y = 180
    for label, value in facts:
        page.insert_text((52, y), label + ":", fontsize=10)
        page.insert_text((188, y), value, fontsize=10)
        y += 25

    page.insert_text((52, y + 18), "Complaint description", fontsize=13)
    description = (
        "Five bottles from one delivered case were leaking around the closure. "
        "The caps appeared loose when the carton was opened. The outer shipping "
        "case was dry and undamaged. No patient used the affected bottles and no "
        "adverse reaction or injury was reported. The pharmacy isolated the units."
    )
    page.insert_textbox(
        pymupdf.Rect(52, y + 34, 543, y + 135),
        description,
        fontsize=10,
        lineheight=1.4,
    )
    page.insert_text((52, y + 170), "Requested action", fontsize=13)
    page.insert_textbox(
        pymupdf.Rect(52, y + 187, 543, y + 255),
        "Please investigate the packaging defect and advise whether the remaining "
        "stock from batch CC26045 may be supplied.",
        fontsize=10,
        lineheight=1.4,
    )

    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), colorspace=pymupdf.csRGB)
    OUTPUT_JPG.write_bytes(pixmap.tobytes("jpeg", jpg_quality=90))

    scan = pymupdf.open()
    scan_page = scan.new_page(width=595, height=842)
    scan_page.insert_image(scan_page.rect, stream=OUTPUT_JPG.read_bytes())
    scan.save(OUTPUT_PDF, deflate=True)


if __name__ == "__main__":
    build()
    print(f"Created {OUTPUT_PDF.name} and {OUTPUT_JPG.name}")
