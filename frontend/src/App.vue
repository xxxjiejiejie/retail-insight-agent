<script setup lang="ts">
import {
  ArrowRight,
  ChatLineRound,
  CircleCheck,
  Collection,
  DataAnalysis,
  Delete,
  Document,
  Download,
  MagicStick,
  Promotion,
  Search,
  Timer,
  TrendCharts,
} from "@element-plus/icons-vue"
import { computed, defineAsyncComponent, nextTick, onMounted, ref } from "vue"

import {
  getHealth,
  getPolicyDetail,
  getPolicyMetadata,
  getSchemaMetadata,
  getSessionHistory,
  streamQuestion,
} from "./api"
import {
  demoPolicyDetails,
  demoPolicyMetadata,
  demoResponses,
  demoSchemaMetadata,
  demoTurn,
} from "./demoData"
import type {
  ChatResponse,
  ChatTurn,
  HealthResponse,
  Intent,
  PolicyDetailResponse,
  PolicyMetadataItem,
  SchemaMetadataResponse,
} from "./types"

const SESSION_STORAGE_KEY = "retail-insight-session-id"
const SESSION_INDEX_STORAGE_KEY = "retail-insight-session-index"
const MAX_TRACKED_SESSIONS = 20
const ChartPanel = defineAsyncComponent(() => import("./components/ChartPanel.vue"))
const EvaluationDashboard = defineAsyncComponent(
  () => import("./components/EvaluationDashboard.vue"),
)

type ResultTab = "overview" | "data" | "evidence" | "trace"
type ServiceState = "checking" | "online" | "offline" | "demo"
type WorkspaceView = "analysis" | "evaluation"

const intentDetails: Record<Intent, { label: string; description: string }> = {
  sql: { label: "经营数据分析", description: "安全 Text-to-SQL" },
  rag: { label: "制度知识问答", description: "检索、重排与引用" },
  hybrid: { label: "综合经营研判", description: "数据与制度并行分析" },
  report: { label: "分析报告生成", description: "受控 ReAct 与工具调用" },
  clarify: { label: "问题澄清", description: "补充必要查询条件" },
  general: { label: "通用问答", description: "智能助手直接回答" },
}

const examples = [
  {
    type: "SQL",
    title: "目标完成分析",
    description: "查看门店表现和异常点",
    query: "2026年6月各门店销售目标完成率是多少？",
    icon: TrendCharts,
  },
  {
    type: "RAG",
    title: "退换货制度",
    description: "获取条款、章节和原文引用",
    query: "普通商品无质量问题可以在多少天内退货？",
    icon: Document,
  },
  {
    type: "HYBRID",
    title: "经营与制度联查",
    description: "一次返回数据结论与制度依据",
    query: "查询2026年6月各门店销售目标完成率，并说明绩效制度中的指标权重",
    icon: MagicStick,
  },
]

const SESSION_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/

function trackedSessionIds(): string[] {
  const raw = localStorage.getItem(SESSION_INDEX_STORAGE_KEY)
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(
      (value): value is string => typeof value === "string" && SESSION_ID_PATTERN.test(value),
    )
  } catch {
    return []
  }
}

function rememberSession(session: string): void {
  const sessions = [session, ...trackedSessionIds().filter((item) => item !== session)].slice(
    0,
    MAX_TRACKED_SESSIONS,
  )
  localStorage.setItem(SESSION_INDEX_STORAGE_KEY, JSON.stringify(sessions))
}

function currentSessionId(): string {
  const stored = localStorage.getItem(SESSION_STORAGE_KEY)
  if (stored && SESSION_ID_PATTERN.test(stored)) {
    rememberSession(stored)
    return stored
  }
  const created = crypto.randomUUID()
  localStorage.setItem(SESSION_STORAGE_KEY, created)
  rememberSession(created)
  return created
}

const query = ref("")
const loading = ref(false)
const loadingStatus = ref("")
const error = ref("")
const result = ref<ChatResponse | null>(null)
const history = ref<ChatTurn[]>([])
const demoHistory = ref<ChatTurn[]>([])
const sessionId = ref(currentSessionId())
const activeTab = ref<ResultTab>("overview")
const copiedSql = ref(false)
const selectedTurnId = ref<string | null>(null)
const workspaceView = ref<WorkspaceView>("analysis")
const isDemoMode = ref(new URLSearchParams(window.location.search).get("demo") === "1")
const drawerKind = ref<"policies" | "schema" | null>(null)
const drawerLoading = ref(false)
const drawerError = ref("")
const policyMetadata = ref<PolicyMetadataItem[]>([])
const selectedPolicy = ref<PolicyDetailResponse | null>(null)
const selectedPolicyRequest = ref<PolicyMetadataItem | null>(null)
const policyDetailLoading = ref(false)
const policyDetailError = ref("")
const schemaMetadata = ref<SchemaMetadataResponse | null>(null)
const health = ref<HealthResponse | null>(null)
const healthLoading = ref(true)
const healthError = ref("")
const schemaStatus = ref<ServiceState>(isDemoMode.value ? "demo" : "checking")
const policyStatus = ref<ServiceState>(isDemoMode.value ? "demo" : "checking")

if (isDemoMode.value) {
  policyMetadata.value = [...demoPolicyMetadata]
  schemaMetadata.value = demoSchemaMetadata
}

const canSend = computed(() => query.value.trim().length >= 2 && !loading.value)
const sqlRows = computed(() => result.value?.sql_result?.rows ?? [])
const sqlColumns = computed(() => result.value?.sql_result?.columns ?? [])
const toolResults = computed(() => result.value?.tool_results ?? [])
const currentIntent = computed(() =>
  intentDetails[result.value?.intent ?? "general"],
)
const displayedHistory = computed(() => (isDemoMode.value ? demoHistory.value : history.value))
const recentHistory = computed(() => [...displayedHistory.value].reverse())
const sessionShortId = computed(() => sessionId.value.slice(0, 8))
const isHistoricalResult = computed(() => Boolean(selectedTurnId.value))
const serviceItems = computed(() => {
  const apiState: ServiceState = isDemoMode.value
    ? "demo"
    : healthLoading.value
      ? "checking"
      : health.value?.status === "ok"
        ? "online"
        : "offline"
  return [
    { label: "API 服务", state: apiState },
    { label: "经营数据库", state: isDemoMode.value ? "demo" : schemaStatus.value },
    { label: "制度知识库", state: isDemoMode.value ? "demo" : policyStatus.value },
  ]
})

function serviceStateLabel(state: ServiceState): string {
  return { checking: "检查中", online: "正常", offline: "异常", demo: "演示" }[state]
}
const resultTabs = computed(() => [
  { id: "overview" as const, label: "分析结论", count: null, disabled: false },
  {
    id: "data" as const,
    label: "数据与图表",
    count: result.value?.sql_result?.row_count ?? null,
    disabled: !result.value?.sql_result,
  },
  {
    id: "evidence" as const,
    label: "制度依据",
    count: result.value?.citations.length ?? null,
    disabled: !result.value?.citations.length,
  },
  { id: "trace" as const, label: "运行轨迹", count: null, disabled: false },
])

const metricItems = computed(() => {
  const metrics = result.value?.metrics
  if (!metrics) return []
  return [
    { label: "总耗时", value: metrics.total_latency_ms, unit: "ms", icon: Timer },
    { label: "LLM 耗时", value: metrics.llm_latency_ms, unit: "ms", icon: MagicStick },
    { label: "SQL 执行", value: metrics.sql_execution_ms, unit: "ms", icon: DataAnalysis },
    { label: "检索耗时", value: metrics.retrieval_ms, unit: "ms", icon: Search },
    { label: "重排耗时", value: metrics.rerank_ms, unit: "ms", icon: Collection },
    { label: "Token", value: metrics.total_tokens, unit: "", icon: Promotion },
    { label: "生成次数", value: metrics.attempt_count, unit: "次", icon: CircleCheck },
    { label: "有效证据", value: metrics.evidence_count, unit: "条", icon: Document },
    { label: "引用数", value: metrics.citation_count, unit: "条", icon: Collection },
    { label: "工具调用", value: metrics.tool_call_count, unit: "次", icon: MagicStick },
    { label: "工具耗时", value: metrics.tool_latency_ms, unit: "ms", icon: Timer },
  ].filter((item) => item.value !== undefined && item.value !== null)
})

const headlineMetrics = computed(() => {
  if (!result.value) return []
  const metrics = result.value.metrics
  return [
    {
      label: "响应耗时",
      value: formatMetric(metrics.total_latency_ms),
      unit: metrics.total_latency_ms == null ? "" : "ms",
    },
    {
      label: "Token 用量",
      value: formatMetric(metrics.total_tokens),
      unit: "",
    },
    {
      label: "数据行数",
      value: formatMetric(result.value.sql_result?.row_count),
      unit: result.value.sql_result ? "行" : "",
    },
    {
      label: "引用证据",
      value: formatMetric(result.value.citations.length),
      unit: "条",
    },
  ]
})

const nodeLabels: Record<string, string> = {
  route: "识别问题意图",
  sql: "生成并执行安全 SQL",
  rag: "检索与重排制度依据",
  hybrid: "并行分析经营数据与制度",
  report_agent: "调用工具生成分析报告",
  clarify: "整理需要补充的条件",
  general: "生成通用回答",
  persist_turn: "保存本轮会话",
}

const pipelineSteps = computed(() => {
  const status = loadingStatus.value
  const routeDone = loading.value && status !== "正在连接分析服务"
  const analysisDone = Boolean(result.value) || status.includes("保存")
  return [
    { label: "理解问题", done: routeDone || analysisDone, active: !routeDone && loading.value },
    { label: "选择工具", done: routeDone, active: routeDone && !analysisDone && loading.value },
    { label: "执行分析", done: analysisDone, active: routeDone && !analysisDone && loading.value },
    { label: "形成结论", done: Boolean(result.value), active: analysisDone && loading.value },
  ]
})

function formatMetric(value: unknown): string {
  if (value === undefined || value === null) return "—"
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString("zh-CN")
      : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
  }
  return String(value)
}

function formatCell(value: unknown): string {
  if (value === undefined || value === null) return "—"
  return typeof value === "number"
    ? value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
    : String(value)
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function applyExample(exampleQuery: string): void {
  workspaceView.value = "analysis"
  query.value = exampleQuery
  window.scrollTo({ top: 0, behavior: "smooth" })
}

function reuseTurn(turn: ChatTurn): void {
  workspaceView.value = "analysis"
  query.value = turn.query
  selectedTurnId.value = turn.turn_id
  result.value = {
    session_id: isDemoMode.value ? "demo-session" : sessionId.value,
    intent: turn.intent,
    resolved_query: turn.resolved_query,
    context_used: turn.context_used,
    answer: turn.answer,
    clarification: turn.clarification,
    generated_sql: turn.generated_sql,
    sql_result: turn.sql_result,
    chart_spec: turn.chart_spec,
    citations: turn.citations,
    tool_calls: turn.tool_calls ?? [],
    tool_results: turn.tool_results ?? [],
    tool_round_count: turn.tool_round_count ?? 0,
    report_artifact: turn.report_artifact,
    errors: turn.errors,
    metrics: turn.metrics,
  }
  activeTab.value = "overview"
  copiedSql.value = false
  window.scrollTo({ top: 0, behavior: "smooth" })
}

function goWorkspace(view: WorkspaceView): void {
  workspaceView.value = view
  closeMetadata()
  window.scrollTo({ top: 0, behavior: "smooth" })
}

async function refreshHistory(): Promise<void> {
  if (isDemoMode.value) return
  rememberSession(sessionId.value)
  const responses = await Promise.allSettled(
    trackedSessionIds().map((trackedId) => getSessionHistory(trackedId)),
  )
  const successfulResponses = responses.flatMap((response) =>
    response.status === "fulfilled" ? [response.value] : [],
  )
  if (successfulResponses.length === 0 && responses.length > 0) return
  const turns = successfulResponses.flatMap((response) => response.turns)
  const uniqueTurns = new Map(turns.map((turn) => [turn.turn_id, turn]))
  history.value = [...uniqueTurns.values()].sort((left, right) =>
    left.created_at.localeCompare(right.created_at),
  )
}

async function checkHealth(): Promise<void> {
  healthLoading.value = true
  healthError.value = ""
  try {
    health.value = await getHealth()
  } catch (reason) {
    health.value = null
    healthError.value = reason instanceof Error ? reason.message : "API 状态检查失败"
  } finally {
    healthLoading.value = false
  }
}

async function loadMetadata(kind: "policies" | "schema"): Promise<void> {
  if (isDemoMode.value) return
  const hasCachedData =
    (kind === "policies" && policyMetadata.value.length > 0) ||
    (kind === "schema" && schemaMetadata.value !== null)
  if (hasCachedData) return

  drawerLoading.value = true
  if (kind === "policies") policyStatus.value = "checking"
  else schemaStatus.value = "checking"
  try {
    if (kind === "policies") {
      policyMetadata.value = (await getPolicyMetadata()).documents
      policyStatus.value = "online"
    } else {
      schemaMetadata.value = await getSchemaMetadata()
      schemaStatus.value = "online"
    }
  } catch (reason) {
    drawerError.value = reason instanceof Error ? reason.message : "元数据读取失败，请稍后重试。"
    if (kind === "policies") policyStatus.value = "offline"
    else schemaStatus.value = "offline"
  } finally {
    drawerLoading.value = false
  }
}

async function openMetadata(kind: "policies" | "schema"): Promise<void> {
  selectedPolicy.value = null
  selectedPolicyRequest.value = null
  policyDetailError.value = ""
  drawerKind.value = kind
  drawerError.value = ""
  await loadMetadata(kind)
}

function closeMetadata(): void {
  drawerKind.value = null
  drawerError.value = ""
  selectedPolicy.value = null
  selectedPolicyRequest.value = null
  policyDetailError.value = ""
}

async function openPolicyDetail(policy: PolicyMetadataItem): Promise<void> {
  selectedPolicyRequest.value = policy
  selectedPolicy.value = null
  policyDetailError.value = ""
  policyDetailLoading.value = true
  try {
    if (isDemoMode.value) {
      const detail = demoPolicyDetails[policy.document_id]
      if (!detail) throw new Error("演示制度正文暂时不可用。")
      selectedPolicy.value = detail
    } else {
      selectedPolicy.value = await getPolicyDetail(policy.document_id)
    }
  } catch (reason) {
    policyDetailError.value =
      reason instanceof Error ? reason.message : "制度正文读取失败，请稍后重试。"
  } finally {
    policyDetailLoading.value = false
  }
}

function closePolicyDetail(): void {
  selectedPolicy.value = null
  selectedPolicyRequest.value = null
  policyDetailError.value = ""
}

function demoResponseFor(queryText: string): ChatResponse {
  if (queryText.includes("报告") || queryText.includes("简报")) return demoResponses.report
  if (queryText.includes("并说明") || queryText.includes("并依据") || queryText.includes("绩效")) {
    return demoResponses.hybrid
  }
  if (queryText.includes("退货") || queryText.includes("制度")) return demoResponses.rag
  return demoResponses.sql
}

async function submitDemo(): Promise<void> {
  const stages = ["识别问题意图", "准备演示数据", "整理分析结果", "形成演示结论"]
  for (const stage of stages) {
    loadingStatus.value = stage
    await new Promise((resolve) => window.setTimeout(resolve, 180))
  }
  const response = demoResponseFor(query.value.trim())
  const turn = demoTurn(response, query.value.trim())
  demoHistory.value = [...demoHistory.value, turn].slice(-20)
  selectedTurnId.value = null
  result.value = { ...response, session_id: "demo-session" }
}

async function toggleDemoMode(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  isDemoMode.value = target.checked
  result.value = null
  selectedTurnId.value = null
  selectedPolicy.value = null
  selectedPolicyRequest.value = null
  policyDetailError.value = ""
  activeTab.value = "overview"
  error.value = ""
  const url = new URL(window.location.href)
  if (isDemoMode.value) {
    url.searchParams.set("demo", "1")
    healthLoading.value = false
    policyMetadata.value = [...demoPolicyMetadata]
    schemaMetadata.value = demoSchemaMetadata
    policyStatus.value = "demo"
    schemaStatus.value = "demo"
  } else {
    url.searchParams.delete("demo")
    policyMetadata.value = []
    schemaMetadata.value = null
    await Promise.all([
      checkHealth(),
      refreshHistory(),
      loadMetadata("policies"),
      loadMetadata("schema"),
    ])
  }
  window.history.replaceState({}, "", url)
}

async function submit(): Promise<void> {
  if (!canSend.value) return
  loading.value = true
  loadingStatus.value = "正在连接分析服务"
  error.value = ""
  activeTab.value = "overview"
  copiedSql.value = false
  selectedTurnId.value = null
  result.value = null
  try {
    if (isDemoMode.value) {
      await submitDemo()
    } else {
      result.value = await streamQuestion(query.value.trim(), sessionId.value, (event, data) => {
        if (event === "node") {
          const node = String(data.node || "")
          loadingStatus.value = nodeLabels[node] || "正在处理"
        } else if (event === "heartbeat") {
          loadingStatus.value = loadingStatus.value || "正在处理"
        }
      })
      await refreshHistory()
    }
    await nextTick()
    document.querySelector("#analysis-result")?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    })
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError") {
      error.value = "请求超过 3 分钟，已自动停止。"
    } else {
      error.value = reason instanceof Error ? reason.message : "请求失败，请检查后端是否启动。"
    }
  } finally {
    loading.value = false
    loadingStatus.value = ""
  }
}

async function clearSession(): Promise<void> {
  error.value = ""
  try {
    if (!isDemoMode.value) rememberSession(sessionId.value)
    sessionId.value = crypto.randomUUID()
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId.value)
    if (!isDemoMode.value) rememberSession(sessionId.value)
    demoHistory.value = []
    result.value = null
    query.value = ""
    activeTab.value = "overview"
    selectedTurnId.value = null
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "清空会话失败。"
  }
}

async function copySql(): Promise<void> {
  if (!result.value?.generated_sql) return
  await navigator.clipboard.writeText(result.value.generated_sql)
  copiedSql.value = true
  window.setTimeout(() => {
    copiedSql.value = false
  }, 1800)
}

function downloadCsv(): void {
  const sqlResult = result.value?.sql_result
  if (!sqlResult) return
  const escapeValue = (value: unknown) => {
    const text = value == null ? "" : String(value)
    return `"${text.replaceAll('"', '""')}"`
  }
  const lines = [
    sqlResult.columns.map(escapeValue).join(","),
    ...sqlResult.rows.map((row) =>
      sqlResult.columns.map((column) => escapeValue(row[column])).join(","),
    ),
  ]
  const blob = new Blob([`\ufeff${lines.join("\r\n")}`], {
    type: "text/csv;charset=utf-8",
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `retail-insight-${new Date().toISOString().slice(0, 10)}.csv`
  anchor.click()
  URL.revokeObjectURL(url)
}

function openReport(): void {
  const artifact = result.value?.report_artifact
  if (!artifact) return
  if (isDemoMode.value) {
    const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${artifact.title}</title><body style="font-family:Arial,'Microsoft YaHei';max-width:860px;margin:40px auto;line-height:1.8"><h1>${artifact.title}</h1><p>演示报告：华东区域两家门店销售目标完成率低于 100%，建议优先复核客流、转化率与促销执行情况。</p><h2>数据说明</h2><p>本文件由前端演示数据生成，不调用模型或真实数据库。</p></body></html>`
    const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }))
    window.open(url, "_blank", "noopener,noreferrer")
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    return
  }
  window.open(artifact.download_url, "_blank", "noopener,noreferrer")
}

onMounted(async () => {
  if (isDemoMode.value) {
    healthLoading.value = false
  } else {
    await Promise.all([
      checkHealth(),
      loadMetadata("policies"),
      loadMetadata("schema"),
    ])
  }
  try {
    await refreshHistory()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "读取会话历史失败。"
  }
})
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><DataAnalysis /></div>
        <div>
          <strong>Retail Insight</strong>
          <span>AI ANALYTICS</span>
        </div>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <button
          class="nav-item"
          :class="{ active: workspaceView === 'analysis' && !drawerKind }"
          type="button"
          @click="goWorkspace('analysis')"
        >
          <DataAnalysis />
          <span>分析工作台</span>
          <span class="nav-indicator" />
        </button>
        <button
          class="nav-item"
          :class="{ active: workspaceView === 'evaluation' && !drawerKind }"
          type="button"
          @click="goWorkspace('evaluation')"
        >
          <TrendCharts />
          <span>评测结果</span>
          <small>历史</small>
        </button>
        <button class="nav-item" type="button" @click="openMetadata('policies')">
          <Document />
          <span>制度知识库</span>
          <small>{{ policyMetadata.length || 8 }} 份</small>
        </button>
        <button class="nav-item" type="button" @click="openMetadata('schema')">
          <Collection />
          <span>经营数据库</span>
          <small>{{ schemaMetadata?.tables.length || 8 }} 表</small>
        </button>
      </nav>

      <section class="sidebar-section recent-section">
        <div class="sidebar-title">
          <span>最近会话</span>
          <span>{{ displayedHistory.length }}</span>
        </div>
        <div v-if="recentHistory.length" class="recent-list">
          <button
            v-for="turn in recentHistory"
            :key="turn.turn_id"
            type="button"
            class="recent-item"
            :class="{ selected: selectedTurnId === turn.turn_id }"
            :data-turn-id="turn.turn_id"
            :title="turn.query"
            @click="reuseTurn(turn)"
          >
            <ChatLineRound />
            <span class="recent-copy">
              <span>{{ turn.query }}</span>
              <small>{{ turn.intent }} · {{ formatDate(turn.created_at) }}</small>
            </span>
          </button>
        </div>
        <p v-else class="sidebar-empty">完成首次分析后，会话会显示在这里。</p>
      </section>

      <div class="sidebar-footer">
        <div class="service-health-list" :title="healthError">
          <div v-for="item in serviceItems" :key="item.label" class="service-health-row">
            <span class="pulse-dot" :class="item.state" />
            <span>{{ item.label }}</span>
            <small>{{ serviceStateLabel(item.state) }}</small>
          </div>
        </div>
        <div class="session-code">{{ isDemoMode ? "DEMO SESSION" : `SESSION ${sessionShortId}` }}</div>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <span class="topbar-kicker">
            {{ workspaceView === "analysis" ? "智能经营中枢" : "质量证据中心" }}
          </span>
          <strong>{{ workspaceView === "analysis" ? "分析工作台" : "评测结果" }}</strong>
        </div>
        <div v-if="workspaceView === 'analysis'" class="topbar-actions">
          <span class="as-of-date"><span /> 数据截止 2026-06-30</span>
          <label class="mode-toggle">
            <input type="checkbox" :checked="isDemoMode" @change="toggleDemoMode" />
            <span class="toggle-track"><span /></span>
            <span>演示模式</span>
          </label>
          <el-button class="new-session-button" @click="clearSession">
            <el-icon><Delete /></el-icon>
            新建会话
          </el-button>
        </div>
        <div v-else class="topbar-actions">
          <span class="as-of-date"><span /> READ-ONLY EVIDENCE</span>
        </div>
      </header>

      <div v-if="workspaceView === 'analysis'" class="workspace-content">
        <div v-if="isDemoMode" class="demo-banner">
          <MagicStick />
          <div>
            <strong>演示模式已开启</strong>
            <span>使用前端内置原创样例，不连接 DeepSeek 和业务数据库，不消耗 Token。</span>
          </div>
        </div>
        <section class="intro">
          <div>
            <p class="eyebrow">ASK YOUR BUSINESS</p>
            <h1>用一句话，看清经营数据与制度依据</h1>
            <p class="intro-copy">
              连接零售业务数据库与企业制度知识库，通过安全 SQL、混合检索和可溯源引用生成管理结论。
            </p>
          </div>
          <div class="capability-strip" aria-label="系统能力">
            <span><CircleCheck /> 只读 SQL</span>
            <span><CircleCheck /> 引用溯源</span>
            <span><CircleCheck /> 多轮会话</span>
          </div>
        </section>

        <section class="prompt-panel">
          <div class="prompt-header">
            <div class="prompt-icon"><MagicStick /></div>
            <div>
              <strong>你想了解什么？</strong>
              <span>支持经营查询、制度问答以及两者组合分析</span>
            </div>
            <span class="shortcut">Ctrl + Enter</span>
          </div>
          <el-input
            v-model="query"
            class="question-input"
            type="textarea"
            :rows="4"
            maxlength="1000"
            resize="none"
            placeholder="例如：查询 2026 年 6 月各门店销售目标完成率，并说明绩效制度中的指标权重"
            @keydown.ctrl.enter="submit"
          />
          <div class="prompt-footer">
            <div class="quick-prompts">
              <button
                v-for="example in examples"
                :key="example.type"
                type="button"
                @click="applyExample(example.query)"
              >
                <span>{{ example.type }}</span>
                {{ example.title }}
              </button>
            </div>
            <el-button
              class="submit-button"
              type="primary"
              :loading="loading"
              :disabled="!canSend"
              @click="submit"
            >
              开始分析
              <el-icon v-if="!loading"><ArrowRight /></el-icon>
            </el-button>
          </div>
        </section>

        <div v-if="loading" class="processing-panel" role="status">
          <div class="processing-heading">
            <div class="processing-orb"><span /></div>
            <div>
              <strong>{{ loadingStatus }}</strong>
              <span>LangGraph 正在编排分析流程，请稍候</span>
            </div>
          </div>
          <div class="pipeline">
            <div
              v-for="(step, index) in pipelineSteps"
              :key="step.label"
              class="pipeline-step"
              :class="{ done: step.done, active: step.active }"
            >
              <span class="step-number">
                <CircleCheck v-if="step.done" />
                <template v-else>{{ index + 1 }}</template>
              </span>
              <span>{{ step.label }}</span>
            </div>
          </div>
        </div>

        <el-alert
          v-if="error"
          class="error-alert"
          :title="error"
          type="error"
          show-icon
          :closable="false"
        />

        <section v-if="!result && !loading" class="starter-grid">
          <button
            v-for="example in examples"
            :key="example.title"
            class="starter-card"
            type="button"
            @click="applyExample(example.query)"
          >
            <span class="starter-icon"><component :is="example.icon" /></span>
            <span class="starter-type">{{ example.type }}</span>
            <strong>{{ example.title }}</strong>
            <p>{{ example.description }}</p>
            <span class="starter-action">使用这个问题 <ArrowRight /></span>
          </button>
        </section>

        <section v-if="result" id="analysis-result" class="result-workspace">
          <header class="result-header">
            <div class="result-title">
              <span class="result-mark"><CircleCheck /></span>
              <div>
                <span>ANALYSIS COMPLETE</span>
                <h2>{{ currentIntent.label }}</h2>
                <p>{{ currentIntent.description }}</p>
              </div>
            </div>
            <div class="result-flags">
              <span class="intent-pill" :class="`intent-${result.intent}`">{{ result.intent }}</span>
              <span v-if="isDemoMode" class="demo-result-pill">演示数据</span>
              <span v-if="isHistoricalResult" class="history-result-pill">历史快照</span>
              <span v-else-if="!isDemoMode" class="current-result-pill">当前分析</span>
              <span v-if="result.context_used" class="context-pill">已使用会话上下文</span>
            </div>
          </header>

          <div class="headline-metrics">
            <div v-for="item in headlineMetrics" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }} <small>{{ item.unit }}</small></strong>
            </div>
          </div>

          <nav class="result-tabs" aria-label="分析结果分区">
            <button
              v-for="tabItem in resultTabs"
              :key="tabItem.id"
              type="button"
              :class="{ active: activeTab === tabItem.id }"
              :disabled="tabItem.disabled"
              @click="activeTab = tabItem.id"
            >
              {{ tabItem.label }}
              <span v-if="tabItem.count !== null">{{ tabItem.count }}</span>
            </button>
          </nav>

          <div v-show="activeTab === 'overview'" class="overview-layout">
            <article class="content-card answer-card">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">EXECUTIVE SUMMARY</span>
                  <h3>智能分析结论</h3>
                </div>
                <ChatLineRound />
              </div>
              <p class="answer">{{ result.answer }}</p>
              <el-alert
                v-if="result.errors.length"
                class="branch-warning"
                title="部分分析分支未完成"
                :description="result.errors.join('、')"
                type="warning"
                show-icon
                :closable="false"
              />
            </article>

            <aside class="overview-side">
              <article v-if="result.sql_result" class="content-card mini-data-card">
                <div class="section-heading compact">
                  <div>
                    <span class="section-kicker">DATA PREVIEW</span>
                    <h3>数据预览</h3>
                  </div>
                  <button type="button" @click="activeTab = 'data'">查看全部</button>
                </div>
                <div class="preview-table">
                  <div class="preview-row preview-head">
                    <span v-for="column in sqlColumns.slice(0, 2)" :key="column">{{ column }}</span>
                  </div>
                  <div
                    v-for="(row, rowIndex) in sqlRows.slice(0, 4)"
                    :key="rowIndex"
                    class="preview-row"
                  >
                    <span v-for="column in sqlColumns.slice(0, 2)" :key="column">
                      {{ formatCell(row[column]) }}
                    </span>
                  </div>
                </div>
              </article>

              <article v-if="result.citations.length" class="content-card mini-evidence-card">
                <div class="section-heading compact">
                  <div>
                    <span class="section-kicker">EVIDENCE</span>
                    <h3>核心依据</h3>
                  </div>
                  <button type="button" @click="activeTab = 'evidence'">查看全部</button>
                </div>
                <strong>{{ result.citations[0].source }}</strong>
                <p>{{ result.citations[0].section || "相关制度章节" }}</p>
                <span v-if="result.citations[0].relevance_score != null">
                  相关度 {{ (result.citations[0].relevance_score * 100).toFixed(1) }}%
                </span>
              </article>

              <article v-if="result.report_artifact" class="content-card report-artifact-card">
                <div class="section-heading compact">
                  <div>
                    <span class="section-kicker">REPORT ARTIFACT</span>
                    <h3>分析报告</h3>
                  </div>
                  <Document />
                </div>
                <strong>{{ result.report_artifact.title }}</strong>
                <p>HTML · 来源轮次 {{ result.report_artifact.source_turn_id.slice(0, 8) }}</p>
                <el-button type="primary" @click="openReport">
                  查看报告
                  <el-icon><ArrowRight /></el-icon>
                </el-button>
              </article>
            </aside>
          </div>

          <div v-show="activeTab === 'data'" class="data-layout">
            <el-alert
              v-if="result.sql_result?.history_truncated"
              title="历史快照仅保留前 100 行，原始总行数仍按查询结果显示。"
              type="info"
              show-icon
              :closable="false"
            />
            <article v-if="result.sql_result" class="content-card chart-card">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">VISUAL ANALYSIS</span>
                  <h3>{{ result.chart_spec?.title || "查询结果可视化" }}</h3>
                </div>
                <el-button class="secondary-action" @click="downloadCsv">
                  <el-icon><Download /></el-icon>
                  导出 CSV
                </el-button>
              </div>
              <ChartPanel :spec="result.chart_spec" :result="result.sql_result" />
            </article>

            <article v-if="result.sql_result" class="content-card table-card">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">QUERY RESULT</span>
                  <h3>明细数据</h3>
                </div>
                <span class="table-summary">
                  {{ result.sql_result.row_count }} 行 · {{ result.sql_result.execution_ms }} ms
                </span>
              </div>
              <el-table :data="sqlRows" stripe max-height="480" class="result-table">
                <el-table-column
                  v-for="column in sqlColumns"
                  :key="column"
                  :prop="column"
                  :label="column"
                  min-width="150"
                  show-overflow-tooltip
                >
                  <template #default="scope">
                    {{ formatCell(scope.row[column]) }}
                  </template>
                </el-table-column>
              </el-table>
            </article>

            <article v-if="result.generated_sql" class="content-card sql-card">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">AUDITABLE SQL</span>
                  <h3>实际执行语句</h3>
                </div>
                <button class="copy-button" type="button" @click="copySql">
                  {{ copiedSql ? "已复制" : "复制 SQL" }}
                </button>
              </div>
              <pre class="code-block"><code>{{ result.generated_sql }}</code></pre>
              <p class="sql-note"><CircleCheck /> 已通过 SQLGlot 只读校验、字段白名单和 LIMIT 检查</p>
            </article>
          </div>

          <div v-show="activeTab === 'evidence'" class="evidence-layout">
            <article
              v-for="(citation, index) in result.citations"
              :key="citation.chunk_id || `${citation.source}-${citation.paragraph_id}`"
              class="content-card evidence-card"
            >
              <div class="evidence-index">{{ String(index + 1).padStart(2, "0") }}</div>
              <div class="evidence-content">
                <div class="evidence-meta">
                  <span>{{ citation.document_id || "POLICY" }}</span>
                  <span v-if="citation.relevance_score != null" class="score-pill">
                    {{ (citation.relevance_score * 100).toFixed(1) }}% 匹配
                  </span>
                </div>
                <h3>{{ citation.source }}</h3>
                <p class="evidence-location">
                  <span v-if="citation.version">版本 {{ citation.version }}</span>
                  <span v-if="citation.section">{{ citation.section }}</span>
                  <span v-if="citation.paragraph_id">{{ citation.paragraph_id }}</span>
                  <span v-if="citation.page">第 {{ citation.page }} 页</span>
                </p>
                <blockquote v-if="citation.excerpt">{{ citation.excerpt }}</blockquote>
              </div>
            </article>
            <div v-if="!result.citations.length" class="empty-result">
              <Document />
              <strong>本次回答没有使用制度引用</strong>
              <p>数据分析问题可能只执行安全 SQL，不经过制度知识库。</p>
            </div>
          </div>

          <div v-show="activeTab === 'trace'" class="trace-layout">
            <article v-if="toolResults.length" class="content-card tool-trace-panel">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">TOOL CALLING</span>
                  <h3>受控工具轨迹</h3>
                </div>
                <MagicStick />
              </div>
              <div class="tool-trace-list">
                <div
                  v-for="(toolResult, index) in toolResults"
                  :key="`${toolResult.tool_name}-${index}`"
                  class="tool-trace-row"
                >
                  <span class="tool-sequence">{{ String(index + 1).padStart(2, "0") }}</span>
                  <div>
                    <strong>{{ toolResult.tool_name }}</strong>
                    <p>{{ JSON.stringify(toolResult.arguments_summary) }}</p>
                  </div>
                  <span class="tool-status" :class="`tool-${toolResult.status}`">
                    {{ toolResult.status === "success" ? "成功" : "失败" }}
                  </span>
                  <time>{{ formatMetric(toolResult.latency_ms) }} ms</time>
                </div>
              </div>
            </article>

            <article class="content-card">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">OBSERVABILITY</span>
                  <h3>运行指标</h3>
                </div>
                <Timer />
              </div>
              <div class="metrics-grid">
                <div v-for="item in metricItems" :key="item.label" class="metric-item">
                  <span class="metric-icon"><component :is="item.icon" /></span>
                  <div>
                    <span>{{ item.label }}</span>
                    <strong>{{ formatMetric(item.value) }} <small>{{ item.unit }}</small></strong>
                  </div>
                </div>
              </div>
            </article>

            <article class="content-card trace-card">
              <div class="section-heading">
                <div>
                  <span class="section-kicker">REQUEST CONTEXT</span>
                  <h3>请求上下文</h3>
                </div>
                <Collection />
              </div>
              <dl class="context-list">
                <div>
                  <dt>原始问题</dt>
                  <dd>{{ query }}</dd>
                </div>
                <div v-if="result.resolved_query">
                  <dt>解析后问题</dt>
                  <dd>{{ result.resolved_query }}</dd>
                </div>
                <div>
                  <dt>路由意图</dt>
                  <dd>{{ currentIntent.label }} / {{ result.intent }}</dd>
                </div>
                <div>
                  <dt>会话上下文</dt>
                  <dd>{{ result.context_used ? "已使用" : "本轮独立分析" }}</dd>
                </div>
              </dl>
            </article>
          </div>
        </section>
      </div>
      <EvaluationDashboard
        v-else
        class="workspace-content evaluation-workspace"
        :demo="isDemoMode"
      />
    </main>

    <button
      v-if="drawerKind"
      class="drawer-backdrop"
      type="button"
      aria-label="关闭信息抽屉"
      @click="closeMetadata"
    />
    <aside v-if="drawerKind" class="metadata-drawer" :aria-label="drawerKind === 'policies' ? '制度知识库' : '经营数据库'">
      <header class="drawer-header">
        <div class="drawer-heading">
          <span class="drawer-icon">
            <Document v-if="drawerKind === 'policies'" />
            <Collection v-else />
          </span>
          <div>
            <span>{{ drawerKind === "policies" ? "POLICY CATALOG" : "SCHEMA CATALOG" }}</span>
            <h2>{{ drawerKind === "policies" ? "制度知识库" : "经营数据库" }}</h2>
          </div>
        </div>
        <button class="drawer-close" type="button" aria-label="关闭" @click="closeMetadata">×</button>
      </header>

      <div class="drawer-summary">
        <CircleCheck />
        <span v-if="drawerKind === 'policies' && selectedPolicy">
          正在阅读 · {{ selectedPolicy.document_id }} · v{{ selectedPolicy.version }}
        </span>
        <span v-else-if="drawerKind === 'policies'">只读目录 · {{ policyMetadata.length }} 份制度</span>
        <span v-else>只读 Schema · {{ schemaMetadata?.tables.length || 0 }} 张表</span>
      </div>

      <div v-if="drawerLoading" class="drawer-state" role="status">
        <span class="drawer-spinner" />
        <strong>正在读取元数据</strong>
        <p>该操作不会调用大模型。</p>
      </div>
      <div v-else-if="drawerError" class="drawer-state error-state">
        <strong>暂时无法读取</strong>
        <p>{{ drawerError }}</p>
        <button type="button" @click="drawerKind && openMetadata(drawerKind)">重新检查</button>
      </div>

      <div v-else-if="policyDetailLoading" class="drawer-state" role="status">
        <span class="drawer-spinner" />
        <strong>正在读取制度正文</strong>
        <p>仅从本地制度库读取，不会调用大模型。</p>
      </div>
      <div v-else-if="policyDetailError" class="drawer-state error-state">
        <strong>暂时无法读取制度正文</strong>
        <p>{{ policyDetailError }}</p>
        <button
          v-if="selectedPolicyRequest"
          type="button"
          @click="openPolicyDetail(selectedPolicyRequest)"
        >
          重新读取
        </button>
        <button type="button" @click="closePolicyDetail">返回制度目录</button>
      </div>

      <div
        v-else-if="drawerKind === 'policies' && selectedPolicy"
        class="metadata-list policy-detail"
      >
        <button class="policy-back" type="button" @click="closePolicyDetail">
          <ArrowRight /> 返回制度目录
        </button>
        <article class="policy-document">
          <div class="policy-document-head">
            <span>{{ selectedPolicy.document_id }}</span>
            <span>v{{ selectedPolicy.version }}</span>
          </div>
          <h3>{{ selectedPolicy.title }}</h3>
          <p>{{ selectedPolicy.source }} · 生效日期 {{ selectedPolicy.effective_date }}</p>

          <section
            v-for="(section, sectionIndex) in selectedPolicy.sections"
            :key="`${selectedPolicy.document_id}-${sectionIndex}`"
            class="policy-section"
          >
            <div class="policy-section-meta">
              <span>章节 {{ sectionIndex + 1 }}</span>
              <span v-if="section.page">第 {{ section.page }} 页</span>
            </div>
            <h4>{{ section.title }}</h4>
            <p>{{ section.content }}</p>
          </section>
        </article>
      </div>

      <div v-else-if="drawerKind === 'policies'" class="metadata-list policy-catalog">
        <button
          v-for="policy in policyMetadata"
          :key="policy.document_id"
          class="metadata-card policy-card"
          type="button"
          @click="openPolicyDetail(policy)"
        >
          <div class="metadata-card-head">
            <span>{{ policy.document_id }}</span>
            <span>v{{ policy.version }}</span>
          </div>
          <h3>{{ policy.title }}</h3>
          <p>{{ policy.source }}</p>
          <div class="metadata-stats">
            <span>{{ policy.section_count }} 个章节</span>
            <span>{{ policy.chunk_count }} 个分块</span>
            <span>{{ policy.effective_date }}</span>
          </div>
          <span class="policy-open-label">查看正文 <ArrowRight /></span>
        </button>
        <div v-if="!policyMetadata.length" class="drawer-state">
          <strong>制度目录为空</strong>
        </div>
      </div>

      <div v-else class="metadata-list schema-catalog">
        <details
          v-for="(table, tableIndex) in schemaMetadata?.tables || []"
          :key="table.name"
          class="schema-table"
          :open="tableIndex === 0"
        >
          <summary>
            <span><DataAnalysis /> {{ table.name }}</span>
            <small>{{ table.columns.length }} 字段</small>
          </summary>
          <div class="schema-columns">
            <div class="schema-column schema-column-head">
              <span>字段</span><span>类型</span><span>可空</span>
            </div>
            <div v-for="column in table.columns" :key="column.name" class="schema-column">
              <code>{{ column.name }}</code>
              <span>{{ column.type }}</span>
              <span>{{ column.nullable ? "是" : "否" }}</span>
            </div>
          </div>
        </details>
        <div v-if="!schemaMetadata?.tables.length" class="drawer-state">
          <strong>数据库目录为空</strong>
        </div>
      </div>

      <footer class="drawer-footer">
        <CircleCheck /> 仅展示公开模拟数据结构，不提供写入或任意 SQL 执行能力。
      </footer>
    </aside>
  </div>
</template>
