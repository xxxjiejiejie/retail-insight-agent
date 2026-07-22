from typing import Any


async def handle_sql_question(query: str) -> dict[str, Any]:
    """SQL branch contract. Real LLM generation and DB execution arrive in phase 2."""

    return {
        "generated_sql": None,
        "sql_validation": None,
        "sql_result": None,
        "chart_spec": None,
        "answer": (
            "已路由到经营数据分析分支，但数据库 Schema、LLM 和只读执行器尚未配置。"
            f"当前收到的问题是：{query}"
        ),
    }

