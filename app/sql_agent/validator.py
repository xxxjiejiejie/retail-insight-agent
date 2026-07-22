from dataclasses import dataclass, field

from sqlglot import exp, parse
from sqlglot.errors import ParseError

FORBIDDEN_NODE_NAMES = {
    "alter",
    "command",
    "copy",
    "create",
    "delete",
    "drop",
    "grant",
    "insert",
    "load",
    "merge",
    "replace",
    "revoke",
    "truncate",
    "update",
}

FORBIDDEN_FUNCTIONS = {
    "read_csv",
    "read_csv_auto",
    "read_json",
    "read_parquet",
    "sqlite_scan",
    "postgres_scan",
    "mysql_scan",
}


@dataclass(slots=True)
class SQLValidationResult:
    is_safe: bool
    normalized_sql: str | None = None
    errors: list[str] = field(default_factory=list)
    referenced_tables: list[str] = field(default_factory=list)


def validate_read_only_sql(
    sql: str,
    *,
    dialect: str = "mysql",
    allowed_tables: set[str] | None = None,
) -> SQLValidationResult:
    if not sql.strip():
        return SQLValidationResult(is_safe=False, errors=["SQL 不能为空"])

    try:
        statements = parse(sql, read=dialect)
    except ParseError as exc:
        return SQLValidationResult(is_safe=False, errors=[f"SQL 无法解析：{exc}"])

    if len(statements) != 1:
        return SQLValidationResult(is_safe=False, errors=["只允许执行一条 SQL"])

    statement = statements[0]
    if statement is None:
        return SQLValidationResult(is_safe=False, errors=["SQL 解析结果为空"])

    errors: list[str] = []

    for node in statement.walk():
        node_name = type(node).__name__.lower()
        if node_name in FORBIDDEN_NODE_NAMES:
            errors.append(f"禁止的 SQL 节点：{node_name}")
        if isinstance(node, exp.Func):
            function_name = node.sql_name().lower()
            if function_name in FORBIDDEN_FUNCTIONS:
                errors.append(f"禁止的函数：{function_name}")

    tables = sorted({table.name for table in statement.find_all(exp.Table) if table.name})
    if allowed_tables is not None:
        disallowed = sorted(set(tables) - allowed_tables)
        if disallowed:
            errors.append(f"访问了未授权的数据表：{', '.join(disallowed)}")

    has_query = statement.find(exp.Select) is not None or isinstance(statement, exp.Select)
    if not has_query:
        errors.append("只允许 SELECT/CTE 查询")

    return SQLValidationResult(
        is_safe=not errors,
        normalized_sql=statement.sql(dialect=dialect) if not errors else None,
        errors=errors,
        referenced_tables=tables,
    )
