from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi import Path as ApiPath
from fastapi.responses import FileResponse

from app.core.config import get_settings

router = APIRouter(prefix="/reports", tags=["reports"])
REPORT_ID = ApiPath(pattern=r"^[0-9a-f]{8}-[0-9a-f-]{27}$")
SESSION_ID = Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")


def delete_session_reports(session_id: str) -> None:
    output_dir = Path(get_settings().report_output_path).resolve()
    if not output_dir.is_dir():
        return
    for metadata_path in output_dir.glob("*.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metadata.get("session_id") != session_id:
            continue
        report_id = metadata_path.stem
        metadata_path.unlink(missing_ok=True)
        (output_dir / f"{report_id}.html").unlink(missing_ok=True)


@router.get("/{report_id}", response_class=FileResponse)
async def get_report(
    report_id: str = REPORT_ID,
    session_id: str = SESSION_ID,
) -> FileResponse:
    output_dir = Path(get_settings().report_output_path).resolve()
    metadata_path = output_dir / f"{report_id}.json"
    report_path = output_dir / f"{report_id}.html"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到报告。",
        ) from None
    if metadata.get("session_id") != session_id or not report_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到报告。",
        )
    return FileResponse(report_path, media_type="text/html; charset=utf-8")
