"""Archive current evaluation reports as an immutable comparison batch."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.evaluation.reports import build_evaluation_run, save_evaluation_run

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="v0.8 当前基线")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--run-id")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run = build_evaluation_run(
        project_root=PROJECT_ROOT,
        report_directory=PROJECT_ROOT / "data" / "runtime",
        eval_directory=PROJECT_ROOT / "data" / "eval",
        label=args.label,
        model=args.model,
        run_id=args.run_id,
    )
    target = save_evaluation_run(
        run,
        PROJECT_ROOT / "data" / "runtime" / "evaluation_runs",
    )
    print(
        f"run_id={run['run_id']} passed={run['total_passed']}/{run['total_cases']} "
        f"failures={len(run['failures'])} report={target}"
    )


if __name__ == "__main__":
    main()
