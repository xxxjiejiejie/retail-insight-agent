"""Execute all reference SQL without making any LLM requests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.database.engine import get_business_engine
from app.database.schema import load_schema_catalog
from app.sql_agent.executor import execute_read_only_sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "data" / "eval" / "sql_smoke_cases.json"


async def main() -> None:
    cases: list[dict[str, str]] = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    engine = get_business_engine()
    try:
        schema = await load_schema_catalog(engine)
        for case in cases:
            result = await execute_read_only_sql(case["reference_sql"], schema, engine=engine)
            print(f"{case['id']} reference_ok=true rows={result.row_count}")
    finally:
        await engine.dispose()
    print(f"summary={len(cases)}/{len(cases)}")


if __name__ == "__main__":
    asyncio.run(main())
