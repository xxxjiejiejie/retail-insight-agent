<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { deleteSession, getSessionHistory, streamQuestion } from "./api"
import ChartPanel from "./components/ChartPanel.vue"
import type { ChatResponse, ChatTurn } from "./types"

const SESSION_STORAGE_KEY = "retail-insight-session-id"

function currentSessionId(): string {
  const stored = localStorage.getItem(SESSION_STORAGE_KEY)
  if (stored && /^[A-Za-z0-9._-]{1,128}$/.test(stored)) return stored
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

const canSend = computed(() => query.value.trim().length >= 2 && !loading.value)
const sqlRows = computed(() => result.value?.sql_result?.rows ?? [])
const sqlColumns = computed(() => result.value?.sql_result?.columns ?? [])
const metricItems = computed(() => {
  const metrics = result.value?.metrics
  if (!metrics) return []
  return [
    { label: "总耗时", value: metrics.total_latency_ms, unit: "ms" },
    { label: "LLM 耗时", value: metrics.llm_latency_ms, unit: "ms" },
    { label: "SQL 耗时", value: metrics.sql_execution_ms, unit: "ms" },
    { label: "检索耗时", value: metrics.retrieval_ms, unit: "ms" },
    { label: "重排耗时", value: metrics.rerank_ms, unit: "ms" },
    { label: "Token", value: metrics.total_tokens, unit: "" },
    { label: "生成次数", value: metrics.attempt_count, unit: "次" },
    { label: "有效证据", value: metrics.evidence_count, unit: "条" },
    { label: "引用数", value: metrics.citation_count, unit: "条" },
  ].filter((item) => item.value !== undefined && item.value !== null)
})

const nodeLabels: Record<string, string> = {
  route: "正在判断问题类型",
  sql: "正在生成并执行安全 SQL",
  rag: "正在检索和重排制度依据",
  hybrid: "正在并行分析经营数据与制度",
  clarify: "正在整理澄清问题",
  general: "正在生成回答",
  persist_turn: "正在保存会话",
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
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "清空会话失败。"
  }
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
  <main class="page-shell">
    <header class="hero">
      <p class="eyebrow">Retail Insight Agent</p>
      <h1>零售经营分析与制度知识问答智能体</h1>
      <p>使用自然语言查询经营数据，或查找企业制度依据。</p>
    </header>

    <el-card class="query-card" shadow="never">
      <el-input
        v-model="query"
        type="textarea"
        :rows="3"
        placeholder="例如：华东区本月销售额是多少？"
        @keydown.ctrl.enter="submit"
      />
      <div class="query-actions">
        <span>{{ loadingStatus || "Ctrl + Enter 发送" }}</span>
        <div class="action-buttons">
          <el-button :disabled="loading" @click="clearSession">清空并新建会话</el-button>
          <el-button type="primary" :loading="loading" :disabled="!canSend" @click="submit">
            提交问题
          </el-button>
        </div>
      </div>
    </el-card>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <el-card v-if="history.length" class="history-card" shadow="never">
      <template #header>
        <div class="card-heading">
          <strong>会话记录</strong>
          <el-tag type="info">{{ history.length }} 轮</el-tag>
        </div>
      </template>
      <ol class="turn-list">
        <li v-for="turn in history" :key="turn.turn_id" class="turn-item">
          <div class="turn-question"><strong>你：</strong>{{ turn.query }}</div>
          <div class="turn-answer"><strong>助手：</strong>{{ turn.answer }}</div>
          <div class="turn-meta">{{ turn.intent }} · {{ new Date(turn.created_at).toLocaleString() }}</div>
        </li>
      </ol>
    </el-card>

    <section v-if="result" class="result-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-heading">
            <strong>回答</strong>
            <el-tag>{{ result.intent }}</el-tag>
          </div>
        </template>
        <p class="answer">{{ result.answer }}</p>
        <el-alert
          v-if="result.errors.length"
          class="branch-warning"
          title="部分能力未完成"
          :description="result.errors.join('、')"
          type="warning"
          show-icon
          :closable="false"
        />
      </el-card>

      <el-card v-if="result.generated_sql" shadow="never">
        <template #header><strong>生成的 SQL</strong></template>
        <pre class="code-block">{{ result.generated_sql }}</pre>
      </el-card>

      <el-card v-if="result.sql_result" shadow="never">
        <template #header>
          <div class="card-heading">
            <strong>查询结果</strong>
            <span>
              {{ result.sql_result.row_count }} 行 · {{ result.sql_result.execution_ms }} ms
            </span>
          </div>
        </template>
        <el-table :data="sqlRows" border stripe max-height="420">
          <el-table-column
            v-for="column in sqlColumns"
            :key="column"
            :prop="column"
            :label="column"
            min-width="140"
            show-overflow-tooltip
          />
        </el-table>
        <ChartPanel :spec="result.chart_spec" :result="result.sql_result" />
      </el-card>

      <el-card v-if="metricItems.length" shadow="never">
        <template #header><strong>运行指标</strong></template>
        <div class="metrics-grid">
          <div v-for="item in metricItems" :key="item.label" class="metric-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }} {{ item.unit }}</strong>
          </div>
        </div>
      </el-card>

      <el-card v-if="result.citations.length" shadow="never">
        <template #header><strong>引用依据</strong></template>
        <ul class="citation-list">
          <li
            v-for="citation in result.citations"
            :key="citation.chunk_id || `${citation.source}-${citation.paragraph_id}`"
          >
            <strong>{{ citation.source }}</strong>
            <span v-if="citation.version"> · v{{ citation.version }}</span>
            <span v-if="citation.section"> · {{ citation.section }}</span>
            <span v-if="citation.paragraph_id"> · {{ citation.paragraph_id }}</span>
            <span v-if="citation.page"> · 第 {{ citation.page }} 页</span>
            <span v-if="citation.relevance_score !== null && citation.relevance_score !== undefined">
              · 相关度 {{ (citation.relevance_score * 100).toFixed(1) }}%
            </span>
            <p v-if="citation.excerpt" class="citation-excerpt">{{ citation.excerpt }}</p>
          </li>
        </ul>
      </el-card>
    </section>
  </main>
</template>
