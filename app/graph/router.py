import re

from app.graph.state import Intent

SQL_KEYWORDS = {
    "销售额",
    "营收",
    "收入",
    "订单数",
    "客单价",
    "退货率",
    "增长",
    "同比",
    "环比",
    "排名",
    "趋势",
    "完成率",
    "毛利",
    "库存量",
    "库存总量",
    "库存金额",
    "多少家",
    "多少件",
    "多少次",
    "多少种",
    "最高",
    "最低",
    "平均",
    "总额",
    "贡献",
    "新注册",
    "开业日期",
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
    "谁审批",
    "谁复核",
    "谁核查",
    "由谁",
    "批准金额",
    "暂停新增投放",
    "无质量问题",
    "签收后",
    "月度全盘",
    "积一分",
    "积分",
    "有效期",
    "信息泄露",
    "顾客信息",
    "价签",
    "绩效",
    "申诉",
    "异常订单",
    "验证码",
    "上报",
}

SQL_ENTITIES = {"销售", "订单", "库存", "门店", "商品", "客户", "区域", "城市", "品牌"}
SQL_QUERY_WORDS = {"查询", "查看", "列出", "统计", "多少", "哪些", "分别", "各"}
HYBRID_HINTS = {"并说明", "同时说明", "并依据", "按照什么制度", "是否符合", "结合", "依据制度"}
TIME_PATTERN = re.compile(r"20\d{2}年|第[一二三四]季度|\d{1,2}月|本月|上月|最近")


def classify_intent(query: str) -> Intent:
    """Deterministic starter router; replace with evaluated LLM routing later."""

    normalized = query.strip().lower()
    short_time_only = bool(TIME_PATTERN.fullmatch(normalized))
    short_ambiguous_followup = len(normalized) <= 8 and normalized.endswith("怎么样")
    if (
        len(normalized) < 4
        or normalized in {"这个呢", "怎么样", "帮我看看"}
        or short_time_only
        or short_ambiguous_followup
    ):
        return "clarify"

    has_sql = any(keyword in normalized for keyword in SQL_KEYWORDS) or (
        any(entity in normalized for entity in SQL_ENTITIES)
        and any(word in normalized for word in SQL_QUERY_WORDS)
    )
    has_rag = any(keyword in normalized for keyword in RAG_KEYWORDS)

    if has_rag:
        has_hybrid_hint = any(hint in normalized for hint in HYBRID_HINTS)
        has_time_reference = bool(TIME_PATTERN.search(normalized))
        has_policy_action = any(
            phrase in normalized
            for phrase in ("如何处理", "怎么处理", "未达标", "异常", "是否符合")
        )
        if has_sql and (has_hybrid_hint or (has_time_reference and has_policy_action)):
            return "hybrid"
        return "rag"
    if has_sql:
        return "sql"
    return "general"
