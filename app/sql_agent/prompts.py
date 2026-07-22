from __future__ import annotations

from datetime import date

SQL_SYSTEM_PROMPT = """你是零售经营分析系统中的 Text-to-SQL 模块。
你的唯一任务是根据给定 MySQL Schema 和用户问题生成一条只读查询。

必须遵守：
1. 只能输出一个 JSON 对象，禁止 Markdown 代码块和额外解释。
2. SQL 只能是 SELECT 或 WITH ... SELECT，禁止任何写操作、DDL 和多语句。
3. 只能使用提供的表和字段，不得猜测不存在的字段。
4. 销售额计算使用 quantity * sale_price * (1 - discount)。
5. 取消订单不计入销售额，默认限定 orders.status = 'completed'。
6. 日期条件必须使用半开区间，例如 >= '2026-06-01' AND < '2026-07-01'。
7. 客单价 = 销售额 / 去重后的订单数；销售目标完成率 = 实际销售额 / revenue_target * 100。
8. 金额、客单价和百分比使用 ROUND(..., 2)，百分比结果的单位是百分数而非小数比率。
9. 给聚合列使用清晰英文别名，只返回回答问题必要的列，便于前端生成图表。

输出结构：
{
  "sql": "SELECT ...",
  "explanation": "一句中文说明查询口径",
  "chart": {
    "type": "bar 或 line 或 pie 或 scatter",
    "title": "中文图表标题",
    "x_field": "结果中的横轴字段",
    "y_field": "结果中的数值字段"
  }
}
不适合画图时 chart 必须为 null。"""


def _shift_month(month_start: date, months: int) -> date:
    month_index = month_start.year * 12 + month_start.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def build_time_context(data_as_of_date: date) -> str:
    current_month_start = data_as_of_date.replace(day=1)
    next_month_start = _shift_month(current_month_start, 1)
    recent_three_months_start = _shift_month(current_month_start, -2)
    return (
        f"数据截止日期：{data_as_of_date.isoformat()}。所有相对时间以该日期为基准，"
        f"不得使用数据库当前时间。\n"
        f"“本月”：[{current_month_start.isoformat()}, {next_month_start.isoformat()})。\n"
        f"“最近三个月”：[{recent_three_months_start.isoformat()}, "
        f"{next_month_start.isoformat()})。"
    )


def build_sql_user_prompt(query: str, schema_context: str, data_as_of_date: date) -> str:
    return f"""数据库 Schema：
{schema_context}

时间口径：
{build_time_context(data_as_of_date)}

用户问题：{query}

请生成符合要求的 JSON。"""


def build_sql_repair_prompt(
    query: str,
    schema_context: str,
    data_as_of_date: date,
    previous_output: str,
    error_message: str,
) -> str:
    return f"""{build_sql_user_prompt(query, schema_context, data_as_of_date)}

上一次输出未通过校验或执行：
{previous_output[:3000]}

失败原因：{error_message[:500]}

请修正后重新输出完整 JSON，不要解释修正过程。"""
