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
    "into",
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
    "load_file",
    "benchmark",
    "sleep",
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
    allowed_columns: dict[str, set[str]] | None = None,
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
            function_name = (
                node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            ).lower()
            if function_name in FORBIDDEN_FUNCTIONS:
                errors.append(f"禁止的函数：{function_name}")

    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE) if cte.alias_or_name}
    tables = sorted(
        {
            table.name
            for table in statement.find_all(exp.Table)
            if table.name and table.name not in cte_names
        }
    )
    if allowed_tables is not None:
        disallowed = sorted(set(tables) - allowed_tables)
        if disallowed:
            errors.append(f"访问了未授权的数据表：{', '.join(disallowed)}")

    if allowed_columns is not None:
        select_aliases = {
            alias.alias for alias in statement.find_all(exp.Alias) if alias.alias
        }
        aliases = {
            (table.alias or table.name): table.name
            for table in statement.find_all(exp.Table)
            if table.name and table.name not in cte_names
        }
        referenced_column_pool = set().union(
            *(allowed_columns.get(table_name, set()) for table_name in tables)
        )
        for column in statement.find_all(exp.Column):
            column_name = column.name
            if not column_name or column_name == "*":
                continue
            if not column.table and column_name in select_aliases:
                continue
            if column.table:
                if column.table in cte_names:
                    continue
                real_table = aliases.get(column.table)
                if real_table is None or column_name not in allowed_columns.get(real_table, set()):
                    errors.append(f"访问了未授权的字段：{column.table}.{column_name}")
            elif column_name not in referenced_column_pool and not cte_names:
                errors.append(f"访问了未授权的字段：{column_name}")

    has_query = statement.find(exp.Select) is not None or isinstance(statement, exp.Select)
    if not has_query:
        errors.append("只允许 SELECT/CTE 查询")

    return SQLValidationResult(
        is_safe=not errors,
        normalized_sql=statement.sql(dialect=dialect) if not errors else None,
        errors=errors,
        referenced_tables=tables,
    )
