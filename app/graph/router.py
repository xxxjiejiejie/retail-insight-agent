from app.graph.state import Intent

SQL_KEYWORDS = {
    "销售",
    "销售额",
    "营收",
    "收入",
    "订单",
    "库存",
    "退货率",
    "增长",
    "同比",
    "环比",
    "门店",
    "商品",
    "客户",
    "排名",
    "趋势",
}

RAG_KEYWORDS = {
    "制度",
    "规定",
    "规范",
    "流程",
    "审批",
    "政策",
    "规则",
    "办法",
    "如何处理",
    "怎么处理",
}


def classify_intent(query: str) -> Intent:
    """Deterministic starter router; replace with evaluated LLM routing later."""

    normalized = query.strip().lower()
    if len(normalized) < 4 or normalized in {"这个呢", "怎么样", "帮我看看"}:
        return "clarify"

    has_sql = any(keyword in normalized for keyword in SQL_KEYWORDS)
    has_rag = any(keyword in normalized for keyword in RAG_KEYWORDS)

    if has_sql and has_rag:
        return "hybrid"
    if has_sql:
        return "sql"
    if has_rag:
        return "rag"
    return "general"

