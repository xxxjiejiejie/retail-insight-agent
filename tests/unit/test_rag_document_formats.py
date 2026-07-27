from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.rag.loader import load_policy_document
from app.rag.models import DocumentSection
from app.rag.ocr import QwenVisionOcrClient


def write_sidecar(path: Path) -> None:
    path.with_suffix(f"{path.suffix}.metadata.json").write_text(
        json.dumps(
            {
                "document_id": "POL-FORMAT-001",
                "title": "多格式制度",
                "version": "1.0",
                "effective_date": "2026-07-01",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_pdf_loader_preserves_page_numbers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "policy.pdf"
    pdf_path.write_bytes(b"fake-pdf-for-mocked-reader")
    write_sidecar(pdf_path)

    class FakePage:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, path: str):
            assert path.endswith("policy.pdf")
            self.pages = [FakePage("第一页制度内容"), FakePage("第二页审批内容")]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))
    document = load_policy_document(pdf_path)

    assert [section.page for section in document.sections] == [1, 2]
    assert document.sections[1].content == "第二页审批内容"


def test_pdf_loader_rejects_scanned_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"fake-pdf-for-mocked-reader")
    write_sidecar(pdf_path)

    class FakeReader:
        def __init__(self, path: str):
            self.pages = [SimpleNamespace(extract_text=lambda: "")]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))
    with pytest.raises(ValueError, match="OCR"):
        load_policy_document(pdf_path)


def test_pdf_loader_uses_ocr_for_scanned_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"fake-pdf-for-mocked-reader")
    write_sidecar(pdf_path)

    class FakeReader:
        def __init__(self, path: str):
            self.pages = [SimpleNamespace(extract_text=lambda: "")]

    class FakeOcrClient:
        def extract_pdf(self, path: Path) -> list[DocumentSection]:
            assert path == pdf_path
            return [DocumentSection(title="OCR page 1", content="recognized policy", page=1)]

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))
    monkeypatch.setattr("app.rag.ocr.get_ocr_client", lambda: FakeOcrClient())

    document = load_policy_document(pdf_path)

    assert document.content == "recognized policy"
    assert document.sections[0].page == 1


def test_qwen_ocr_client_uses_openai_compatible_vision_request() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["authorization"] = request.headers["Authorization"]
        body = json.loads(request.content)
        seen["model"] = body["model"]
        seen["image_url"] = body["messages"][0]["content"][1]["image_url"]["url"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "OCR result"}}]})

    settings = Settings(
        ocr_enabled=True,
        ocr_provider="qwen_openai_compatible",
        ocr_api_key="test-only-key",
        ocr_base_url="https://example.test/compatible-mode/v1",
    )
    client = QwenVisionOcrClient(settings, transport=httpx.MockTransport(handler))

    assert client.extract_page(b"fake-png", page_number=1) == "OCR result"
    assert seen == {
        "path": "/compatible-mode/v1/chat/completions",
        "authorization": "Bearer test-only-key",
        "model": "qwen3.7-plus",
        "image_url": "data:image/png;base64,ZmFrZS1wbmc=",
    }


def test_docx_loader_extracts_headings_paragraphs_and_tables(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    docx_path = tmp_path / "policy.docx"
    write_sidecar(docx_path)
    document = docx.Document()
    document.add_heading("审批规则", level=1)
    document.add_paragraph("预算超过两万元需要总监审批。")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "审批层级"
    table.cell(0, 1).text = "运营总监"
    document.save(docx_path)

    loaded = load_policy_document(docx_path)

    assert loaded.sections[0].title == "审批规则"
    assert "预算超过两万元" in loaded.sections[0].content
    assert "审批层级 | 运营总监" in loaded.sections[0].content


def test_binary_document_requires_explicit_sidecar_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "policy.pdf"
    pdf_path.write_bytes(b"fake")

    with pytest.raises(ValueError, match="元数据侧车文件"):
        load_policy_document(pdf_path)
