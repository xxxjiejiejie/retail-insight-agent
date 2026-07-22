<script setup lang="ts">
import { computed, ref } from "vue"

import { sendQuestion } from "./api"
import ChartPanel from "./components/ChartPanel.vue"
import type { ChatResponse } from "./types"

const query = ref("")
const loading = ref(false)
const error = ref("")
const result = ref<ChatResponse | null>(null)
const sessionId = crypto.randomUUID()

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
    { label: "引用数", value: metrics.citation_count, unit: "条" },
  ].filter((item) => item.value !== undefined)
})

async function submit(): Promise<void> {
  if (!canSend.value) return
  loading.value = true
  error.value = ""
  try {
    result.value = await sendQuestion(query.value.trim(), sessionId)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "请求失败，请检查后端是否启动。"
  } finally {
    loading.value = false
  }
}
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
        <span>Ctrl + Enter 发送</span>
        <el-button type="primary" :loading="loading" :disabled="!canSend" @click="submit">
          提交问题
        </el-button>
      </div>
    </el-card>

    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

    <section v-if="result" class="result-grid">
      <el-card shadow="never">
        <template #header>
          <div class="card-heading">
            <strong>回答</strong>
            <el-tag>{{ result.intent }}</el-tag>
          </div>
        </template>
        <p class="answer">{{ result.answer }}</p>
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
            <p v-if="citation.excerpt" class="citation-excerpt">{{ citation.excerpt }}</p>
          </li>
        </ul>
      </el-card>
    </section>
  </main>
</template>
