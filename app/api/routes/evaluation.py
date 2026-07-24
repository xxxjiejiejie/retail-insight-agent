from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.api.schemas import (
    EvaluationRunListResponse,
    EvaluationRunResponse,
    EvaluationRunSummaryResponse,
)
from app.core.config import get_settings
from app.evaluation.reports import load_evaluation_run, load_evaluation_runs

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


def _run_directory() -> Path:
    return Path(get_settings().evaluation_runs_path)


@router.get("/runs", response_model=EvaluationRunListResponse)
async def get_evaluation_runs() -> EvaluationRunListResponse:
    try:
        runs = load_evaluation_runs(_run_directory())
        summaries = [EvaluationRunSummaryResponse.model_validate(run) for run in runs]
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="评测批次暂时不可用。",
        ) from exc
    return EvaluationRunListResponse(runs=summaries)


@router.get("/runs/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run(run_id: str) -> EvaluationRunResponse:
    try:
        run = load_evaluation_run(_run_directory(), run_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="评测批次暂时不可用。",
        ) from exc
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到评测批次。",
        )
    return EvaluationRunResponse.model_validate(run)
