from dataclasses import dataclass, field

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, traverse_scope

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
        for scope in traverse_scope(statement):
            source_columns: dict[str, set[str]] = {}
            for source_alias, source in scope.sources.items():
                if isinstance(source, exp.Table):
                    source_columns[source_alias] = allowed_columns.get(source.name, set())
                elif isinstance(source, Scope):
                    selected_expressions = source.expression.args.get("expressions") or []
                    source_columns[source_alias] = {
                        selected.alias_or_name
                        for selected in selected_expressions
                        if isinstance(selected, exp.Expr) and selected.alias_or_name
                    }

            selected_expressions = scope.expression.args.get("expressions") or []
            projection_aliases = {
                selected.alias
                for selected in selected_expressions
                if isinstance(selected, exp.Expr) and selected.alias
            }
            unqualified_column_pool = {
                *set().union(*source_columns.values()),
                *projection_aliases,
            }
            for column in scope.columns:
                column_name = column.name
                if not column_name or column_name == "*":
                    continue
                if column.table:
                    permitted = source_columns.get(column.table)
                    if permitted is None or column_name not in permitted:
                        error = f"访问了未授权的字段：{column.table}.{column_name}"
                        if error not in errors:
                            errors.append(error)
                elif column_name not in unqualified_column_pool:
                    error = f"访问了未授权的字段：{column_name}"
                    if error not in errors:
                        errors.append(error)

    has_query = statement.find(exp.Select) is not None or isinstance(statement, exp.Select)
    if not has_query:
        errors.append("只允许 SELECT/CTE 查询")

    return SQLValidationResult(
        is_safe=not errors,
        normalized_sql=statement.sql(dialect=dialect) if not errors else None,
        errors=errors,
        referenced_tables=tables,
    )
