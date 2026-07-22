from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


def checkpoint_path(database_url: str) -> str:
    """Convert the configured SQLite URL into the path expected by aiosqlite."""

    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if database_url.startswith(prefix):
            return database_url.removeprefix(prefix)
    if "://" in database_url:
        raise ValueError("SESSION_DATABASE_URL must use SQLite for local checkpoints")
    return database_url


@asynccontextmanager
async def open_checkpointer(database_url: str) -> AsyncIterator[AsyncSqliteSaver]:
    path = checkpoint_path(database_url)
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as connection:
        serializer = JsonPlusSerializer(allowed_msgpack_modules=())
        saver = AsyncSqliteSaver(connection, serde=serializer)
        await saver.setup()
        yield saver
