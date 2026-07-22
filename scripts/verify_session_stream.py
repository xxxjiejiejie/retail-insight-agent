"""Verify SSE progress events and persisted session history through the public API."""

from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8080/api/v1")
    parser.add_argument("--session-id", default="compose-persistence-check")
    parser.add_argument("--query", default="你好，你能做什么？")
    parser.add_argument("--reset", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with httpx.AsyncClient(base_url=args.base_url, timeout=180) as client:
        if args.reset:
            reset_response = await client.delete(f"/sessions/{args.session_id}")
            reset_response.raise_for_status()

        events: list[tuple[str, float]] = []
        final_result: dict[str, Any] | None = None
        started = perf_counter()
        async with client.stream(
            "POST",
            "/chat/stream",
            json={"query": args.query, "session_id": args.session_id},
        ) as response:
            response.raise_for_status()
            event_name = "message"
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_name = line.removeprefix("event:").strip()
                elif line.startswith("data:"):
                    payload = json.loads(line.removeprefix("data:").strip())
                    elapsed_ms = round((perf_counter() - started) * 1000, 2)
                    events.append((event_name, elapsed_ms))
                    if event_name == "result":
                        final_result = payload

        history_response = await client.get(f"/sessions/{args.session_id}")
        history_response.raise_for_status()
        history = history_response.json()

    event_names = [event for event, _ in events]
    required = {"start", "node", "result", "done"}
    missing = required.difference(event_names)
    if missing or final_result is None:
        raise RuntimeError(f"missing SSE events: {sorted(missing)}")

    safe_result = {
        "session_id": args.session_id,
        "events": events,
        "intent": final_result.get("intent"),
        "errors": final_result.get("errors", []),
        "persisted_turns": len(history.get("turns", [])),
    }
    print(json.dumps(safe_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
