"""Send one harmless image-only PDF page to the configured OCR service."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import fitz

from app.core.config import get_settings
from app.rag.loader import load_policy_document
from app.rag.ocr import get_ocr_client


def _make_smoke_pdf(path: Path) -> None:
    """Create an image-only page so pypdf cannot use a native text layer."""

    svg = b"""<svg xmlns='http://www.w3.org/2000/svg' width='900' height='500'>
    <rect width='100%' height='100%' fill='white'/>
    <text x='70' y='130' font-family='Arial' font-size='52'>OCR smoke test</text>
    <text x='70' y='250' font-family='Arial' font-size='38'>Date: 2026-07-27</text>
    <text x='70' y='340' font-family='Arial' font-size='38'>Amount: 128.50 CNY</text>
    </svg>"""
    image_document = fitz.open("svg", svg)
    try:
        png = image_document[0].get_pixmap(alpha=False).tobytes("png")
    finally:
        image_document.close()

    pdf = fitz.open()
    try:
        page = pdf.new_page(width=900, height=500)
        page.insert_image(page.rect, stream=png)
        pdf.save(path)
    finally:
        pdf.close()
    path.with_suffix(".pdf.metadata.json").write_text(
        json.dumps(
            {
                "document_id": "OCR-SMOKE-001",
                "title": "OCR Smoke Test",
                "version": "1.0",
                "effective_date": "2026-07-27",
            }
        ),
        encoding="utf-8",
    )


def main() -> None:
    settings = get_settings()
    client = get_ocr_client()
    if client is None:
        raise SystemExit(
            "OCR is not enabled. Set OCR_ENABLED=true and configure OCR_API_KEY locally."
        )

    with tempfile.TemporaryDirectory(prefix="retail-ocr-smoke-") as directory:
        pdf_path = Path(directory) / "ocr-smoke.pdf"
        _make_smoke_pdf(pdf_path)
        document = load_policy_document(pdf_path)

    text = "\n".join(section.content for section in document.sections)
    expected = ("OCR", "2026", "128")
    matched = sum(token.lower() in text.lower() for token in expected)
    print(
        "OCR smoke verification complete: "
        f"model={settings.ocr_model}, pages={len(document.sections)}, "
        f"expected_tokens={matched}/{len(expected)}"
    )
    if matched < len(expected):
        raise SystemExit("OCR response did not contain all harmless smoke-test tokens.")


if __name__ == "__main__":
    main()
