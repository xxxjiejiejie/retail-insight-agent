"""Run one real grounded RAG answer without exposing credentials."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.rag.service import handle_rag_question


async def main(question: str) -> None:
    result = await handle_rag_question(question)
    safe_result = {
        "question": question,
        "answer": result.get("answer"),
        "citations": result.get("citations", []),
        "errors": result.get("errors", []),
        "metrics": result.get("metrics", {}),
    }
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "question",
        nargs="?",
        default="自然消费积分的有效期是多久？",
    )
    args = parser.parse_args()
    asyncio.run(main(args.question))
