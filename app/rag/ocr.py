"""Optional Qwen Vision OCR fallback for scanned policy PDFs."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.rag.models import DocumentSection

OCR_PROMPT = (
    "你是制度文档 OCR 工具。请逐字转写图片中的中文和英文文本；"
    "保留段落、编号、日期、金额和表格行。不要解释、总结、补充或改写；"
    "无法识别处标记为[无法识别]。"
)


class QwenVisionOcrClient:
    """Use Alibaba Cloud Model Studio's OpenAI-compatible vision endpoint."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if settings.ocr_provider not in {"qwen_openai_compatible", "multimodal"}:
            raise ValueError(f"不支持的 OCR_PROVIDER：{settings.ocr_provider}")
        if not settings.ocr_available:
            raise ValueError("OCR 未启用或 OCR_API_KEY 未配置")
        self._settings = settings
        self._transport = transport

    def extract_pdf(self, path: Path) -> list[DocumentSection]:
        """Render every page and preserve its original page number in the result."""

        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("扫描版 PDF OCR 需要 PyMuPDF，请安装项目的 rag 可选依赖") from exc

        document = fitz.open(path)
        try:
            if document.page_count > self._settings.ocr_max_pages:
                raise ValueError(
                    f"{path.name} 共 {document.page_count} 页，超过 OCR_MAX_PAGES="
                    f"{self._settings.ocr_max_pages} 的安全上限"
                )
            sections: list[DocumentSection] = []
            for page_number in range(1, document.page_count + 1):
                page = document.load_page(page_number - 1)
                image = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
                text = self.extract_page(image, page_number=page_number)
                if text:
                    sections.append(
                        DocumentSection(
                            title=f"第 {page_number} 页（OCR）",
                            content=text,
                            page=page_number,
                        )
                    )
            if not sections:
                raise ValueError(f"{path.name} OCR 后仍未提取到可检索文本")
            return sections
        finally:
            document.close()

    def extract_page(self, png_bytes: bytes, *, page_number: int) -> str:
        data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        payload = {
            "model": self._settings.ocr_model,
            "temperature": 0,
            "max_tokens": self._settings.ocr_max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }
        endpoint = f"{self._settings.ocr_base_url.rstrip('/')}/chat/completions"
        try:
            with httpx.Client(
                timeout=self._settings.ocr_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self._settings.ocr_api_key}"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"第 {page_number} 页 OCR 请求超时") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"第 {page_number} 页 OCR 请求失败（HTTP {exc.response.status_code}）"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"第 {page_number} 页 OCR 服务不可用") from exc

        try:
            data: Any = response.json()
            content = data["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"第 {page_number} 页 OCR 返回格式异常") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"第 {page_number} 页 OCR 未返回文本")
        return content.strip()


def get_ocr_client() -> QwenVisionOcrClient | None:
    """Return a client only when OCR is explicitly enabled and keyed locally."""

    settings = get_settings()
    if not settings.ocr_available:
        return None
    return QwenVisionOcrClient(settings)
