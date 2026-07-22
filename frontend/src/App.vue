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
        <template #header><strong>查询结果</strong></template>
        <pre class="code-block">{{ JSON.stringify(result.sql_result, null, 2) }}</pre>
        <ChartPanel :spec="result.chart_spec" :result="result.sql_result" />
      </el-card>

      <el-card v-if="result.citations.length" shadow="never">
        <template #header><strong>引用依据</strong></template>
        <ul>
          <li v-for="citation in result.citations" :key="`${citation.source}-${citation.page}`">
            {{ citation.source }}
            <span v-if="citation.section"> · {{ citation.section }}</span>
            <span v-if="citation.page"> · 第 {{ citation.page }} 页</span>
          </li>
        </ul>
      </el-card>
    </section>
  </main>
</template>

