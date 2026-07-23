import type {
  ChatResponse,
  ChatTurn,
  PolicyMetadataItem,
  SchemaMetadataResponse,
} from "./types"

const demoSessionId = "demo-session"

export const demoPolicyMetadata: PolicyMetadataItem[] = [
  ["POL-RETURN-001", "商品退换货处理规范", 4, 3],
  ["POL-PROMO-001", "促销活动审批管理办法", 4, 3],
  ["POL-INVENTORY-001", "库存盘点管理制度", 4, 3],
  ["POL-MEMBER-001", "会员积分管理办法", 4, 3],
  ["POL-PRIVACY-001", "客户隐私保护制度", 4, 3],
  ["POL-PERFORMANCE-001", "门店绩效考核办法", 4, 3],
  ["POL-PRICE-001", "商品定价管理制度", 4, 3],
  ["POL-ORDER-001", "异常订单处理规范", 4, 3],
].map(([documentId, title, sectionCount, chunkCount]) => ({
  document_id: String(documentId),
  title: String(title),
  version: "1.0",
  effective_date: "2026-01-01",
  source: "演示目录",
  section_count: Number(sectionCount),
  chunk_count: Number(chunkCount),
}))

export const demoSchemaMetadata: SchemaMetadataResponse = {
  tables: [
    ["stores", ["store_id", "store_name", "region"]],
    ["products", ["product_id", "product_name", "category"]],
    ["customers", ["customer_id", "customer_level", "region"]],
    ["orders", ["order_id", "store_id", "order_date", "status"]],
    ["order_items", ["order_item_id", "order_id", "quantity", "sale_price"]],
    ["inventory", ["store_id", "product_id", "stock_qty", "snapshot_date"]],
    ["sales_targets", ["store_id", "target_month", "revenue_target"]],
    ["returns", ["return_id", "order_id", "return_reason", "return_date"]],
  ].map(([name, columns]) => ({
    name: String(name),
    columns: (columns as string[]).map((column) => ({
      name: column,
      type: column.endsWith("_id") || column.includes("qty") ? "INTEGER" : "VARCHAR/DATE",
      nullable: false,
    })),
  })),
}

export const demoResponses: Record<string, ChatResponse> = {
  sql: {
    session_id: demoSessionId,
    intent: "sql",
    resolved_query: "2026年6月各门店销售目标完成率是多少？",
    context_used: false,
    answer: "演示查询完成：华东区域整体完成率较低，上海悦享店和杭州悦享店需要重点关注。\n\n这是本地演示数据，不会连接真实数据库。",
    generated_sql:
      "SELECT st.store_name, ROUND(SUM(oi.quantity * oi.sale_price * (1 - oi.discount)) / st.revenue_target * 100, 2) AS completion_rate FROM sales_targets AS st JOIN stores ON stores.store_id = st.store_id JOIN orders AS o ON o.store_id = st.store_id JOIN order_items AS oi ON oi.order_id = o.order_id WHERE st.target_month = '2026-06-01' GROUP BY st.store_name, st.revenue_target ORDER BY completion_rate LIMIT 500",
    sql_result: {
      columns: ["store_name", "completion_rate"],
      rows: [
        { store_name: "上海悦享店", completion_rate: 82.4 },
        { store_name: "杭州悦享店", completion_rate: 91.7 },
        { store_name: "南京中心店", completion_rate: 104.2 },
        { store_name: "广州万象店", completion_rate: 112.8 },
      ],
      row_count: 4,
      execution_ms: 18.4,
      executed_sql: "SELECT ... LIMIT 500",
    },
    chart_spec: {
      type: "bar",
      title: "门店销售目标完成率（演示）",
      x_field: "store_name",
      y_field: "completion_rate",
    },
    citations: [],
    errors: [],
    metrics: {
      attempt_count: 1,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      sql_execution_ms: 18.4,
      total_latency_ms: 420,
      context_used: false,
    },
  },
  rag: {
    session_id: demoSessionId,
    intent: "rag",
    resolved_query: "普通商品无质量问题可以在多少天内退货？",
    context_used: false,
    answer: "普通商品无质量问题，顾客可在签收后七日内办理退货。[1]\n\n这是本地演示数据，不会调用 DeepSeek。",
    generated_sql: null,
    sql_result: null,
    chart_spec: null,
    citations: [
      {
        source: "商品退换货处理规范",
        section: "受理条件",
        paragraph_id: "POL-RETURN-001-S01-P01",
        document_id: "POL-RETURN-001",
        version: "1.0",
        excerpt: "普通商品无质量问题的，顾客可在签收后七日内申请退货。",
        relevance_score: 0.996,
      },
    ],
    errors: [],
    metrics: {
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      retrieval_ms: 14.2,
      rerank_ms: 24.8,
      evidence_count: 1,
      citation_count: 1,
      total_latency_ms: 380,
      context_used: false,
    },
  },
  hybrid: {
    session_id: demoSessionId,
    intent: "hybrid",
    resolved_query: "查询2026年6月各门店销售目标完成率，并说明绩效制度中的指标权重",
    context_used: false,
    answer: "演示数据：4 家门店完成率低于 100%，建议优先关注上海悦享店。\n\n绩效制度将销售目标完成率权重设为 60%。[1]\n\n这是本地演示数据，不会调用 DeepSeek。",
    generated_sql: "SELECT store_name, completion_rate FROM demo_sales_target LIMIT 500",
    sql_result: {
      columns: ["store_name", "completion_rate"],
      rows: [
        { store_name: "上海悦享店", completion_rate: 82.4 },
        { store_name: "杭州悦享店", completion_rate: 91.7 },
        { store_name: "南京中心店", completion_rate: 104.2 },
        { store_name: "广州万象店", completion_rate: 112.8 },
      ],
      row_count: 4,
      execution_ms: 18.4,
      executed_sql: "SELECT store_name, completion_rate FROM demo_sales_target LIMIT 500",
    },
    chart_spec: {
      type: "bar",
      title: "销售目标完成率（演示）",
      x_field: "store_name",
      y_field: "completion_rate",
    },
    citations: [
      {
        source: "绩效考核管理办法",
        section: "指标权重",
        paragraph_id: "POL-PERFORMANCE-001-S02-P01",
        document_id: "POL-PERFORMANCE-001",
        version: "1.0",
        excerpt: "销售目标完成率在门店月度绩效考核中占 60% 权重。",
        relevance_score: 0.984,
      },
    ],
    errors: [],
    metrics: {
      attempt_count: 2,
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      sql_execution_ms: 18.4,
      retrieval_ms: 14.2,
      rerank_ms: 24.8,
      evidence_count: 1,
      citation_count: 1,
      total_latency_ms: 430,
      context_used: false,
    },
  },
}

export function demoTurn(response: ChatResponse, query: string): ChatTurn {
  return {
    turn_id: `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    created_at: new Date().toISOString(),
    query,
    resolved_query: response.resolved_query,
    context_used: response.context_used,
    intent: response.intent,
    answer: response.answer,
    clarification: response.clarification,
    generated_sql: response.generated_sql,
    sql_result: response.sql_result,
    chart_spec: response.chart_spec,
    citations: response.citations,
    errors: response.errors,
    metrics: response.metrics,
  }
}
