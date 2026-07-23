from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import ReflectedColumn
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import DatabaseQueryError
from app.database.engine import get_business_engine


@dataclass(slots=True, frozen=True)
class SchemaColumn:
    name: str
    type: str
    nullable: bool


@dataclass(slots=True, frozen=True)
class SchemaCatalog:
    columns: dict[str, set[str]]
    context: str
    details: dict[str, list[SchemaColumn]] = field(default_factory=dict)

    @property
    def tables(self) -> set[str]:
        return set(self.columns)


def _inspect_schema(sync_connection: Connection) -> dict[str, list[ReflectedColumn]]:
    inspector = inspect(sync_connection)
    if inspector is None:
        raise RuntimeError("无法创建数据库 Schema Inspector")
    return {
        table_name: inspector.get_columns(table_name)
        for table_name in sorted(inspector.get_table_names())
    }


async def load_schema_catalog(engine: AsyncEngine | None = None) -> SchemaCatalog:
    business_engine = engine or get_business_engine()
    try:
        async with business_engine.connect() as connection:
            raw_schema = await connection.run_sync(_inspect_schema)
    except SQLAlchemyError as exc:
        raise DatabaseQueryError("无法读取业务数据库 Schema") from exc

    column_map: dict[str, set[str]] = {}
    detail_map: dict[str, list[SchemaColumn]] = {}
    lines: list[str] = []
    for table_name, columns in raw_schema.items():
        column_map[table_name] = {str(column["name"]) for column in columns}
        detail_map[table_name] = [
            SchemaColumn(
                name=str(column["name"]),
                type=str(column["type"]),
                nullable=bool(column.get("nullable", True)),
            )
            for column in columns
        ]
        descriptions = [
            f"{column['name']} {column['type']}"
            + (" NOT NULL" if not column.get("nullable", True) else "")
            for column in columns
        ]
        lines.append(f"TABLE {table_name} ({', '.join(descriptions)})")
    return SchemaCatalog(
        columns=column_map,
        context="\n".join(lines),
        details=detail_map,
    )
