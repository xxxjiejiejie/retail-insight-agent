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

import { deleteSession, getSessionHistory, streamQuestion } from "./api"
import type { ChatResponse, ChatTurn, Intent } from "./types"

const SESSION_STORAGE_KEY = "retail-insight-session-id"
const ChartPanel = defineAsyncComponent(() => import("./components/ChartPanel.vue"))

type ResultTab = "overview" | "data" | "evidence" | "trace"

const intentDetails: Record<Intent, { label: string; description: string }> = {
  sql: { label: "经营数据分析", description: "安全 Text-to-SQL" },
  rag: { label: "制度知识问答", description: "检索、重排与引用" },
  hybrid: { label: "综合经营研判", description: "数据与制度并行分析" },
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

function currentSessionId(): string {
  const stored = localStorage.getItem(SESSION_STORAGE_KEY)
  if (stored && SESSION_ID_PATTERN.test(stored)) return stored
  const created = crypto.randomUUID()
  localStorage.setItem(SESSION_STORAGE_KEY, created)
  return created
}

const query = ref("")
const loading = ref(false)
const loadingStatus = ref("")
const error = ref("")
const result = ref<ChatResponse | null>(null)
const history = ref<ChatTurn[]>([])
const sessionId = ref(currentSessionId())
const activeTab = ref<ResultTab>("overview")
const copiedSql = ref(false)

const canSend = computed(() => query.value.trim().length >= 2 && !loading.value)
const sqlRows = computed(() => result.value?.sql_result?.rows ?? [])
const sqlColumns = computed(() => result.value?.sql_result?.columns ?? [])
const currentIntent = computed(() =>
  intentDetails[result.value?.intent ?? "general"],
)
const recentHistory = computed(() => [...history.value].reverse().slice(0, 5))
const sessionShortId = computed(() => sessionId.value.slice(0, 8))
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
  query.value = exampleQuery
  window.scrollTo({ top: 0, behavior: "smooth" })
}

function reuseTurn(turn: ChatTurn): void {
  query.value = turn.query
  window.scrollTo({ top: 0, behavior: "smooth" })
}

async function refreshHistory(): Promise<void> {
  const response = await getSessionHistory(sessionId.value)
  history.value = response.turns
}

async function submit(): Promise<void> {
  if (!canSend.value) return
  loading.value = true
  loadingStatus.value = "正在连接分析服务"
  error.value = ""
  activeTab.value = "overview"
  copiedSql.value = false
  result.value = null
  try {
    result.value = await streamQuestion(query.value.trim(), sessionId.value, (event, data) => {
      if (event === "node") {
        const node = String(data.node || "")
        loadingStatus.value = nodeLabels[node] || "正在处理"
      } else if (event === "heartbeat") {
        loadingStatus.value = loadingStatus.value || "正在处理"
      }
    })
    await refreshHistory()
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
    await deleteSession(sessionId.value)
    sessionId.value = crypto.randomUUID()
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId.value)
    history.value = []
    result.value = null
    query.value = ""
    activeTab.value = "overview"
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

onMounted(async () => {
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
        <button class="nav-item active" type="button">
          <DataAnalysis />
          <span>分析工作台</span>
          <span class="nav-indicator" />
        </button>
        <div class="nav-item static">
          <Document />
          <span>制度知识库</span>
          <small>8 份</small>
        </div>
        <div class="nav-item static">
          <Collection />
          <span>经营数据库</span>
          <small>8 表</small>
        </div>
      </nav>

      <section class="sidebar-section recent-section">
        <div class="sidebar-title">
          <span>最近会话</span>
          <span>{{ history.length }}</span>
        </div>
        <div v-if="recentHistory.length" class="recent-list">
          <button
            v-for="turn in recentHistory"
            :key="turn.turn_id"
            type="button"
            class="recent-item"
            :title="turn.query"
            @click="reuseTurn(turn)"
          >
            <ChatLineRound />
            <span>{{ turn.query }}</span>
          </button>
        </div>
        <p v-else class="sidebar-empty">完成首次分析后，会话会显示在这里。</p>
      </section>

      <div class="sidebar-footer">
        <div class="service-health">
          <span class="pulse-dot" />
          <div>
            <strong>服务运行正常</strong>
            <span>MySQL · DeepSeek · BGE</span>
          </div>
        </div>
        <div class="session-code">SESSION {{ sessionShortId }}</div>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <span class="topbar-kicker">智能经营中枢</span>
          <strong>分析工作台</strong>
        </div>
        <div class="topbar-actions">
          <span class="as-of-date"><span /> 数据截止 2026-06-30</span>
          <el-button class="new-session-button" @click="clearSession">
            <el-icon><Delete /></el-icon>
            新建会话
          </el-button>
        </div>
      </header>

      <div class="workspace-content">
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
            </aside>
          </div>

          <div v-show="activeTab === 'data'" class="data-layout">
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
    </main>
  </div>
</template>
