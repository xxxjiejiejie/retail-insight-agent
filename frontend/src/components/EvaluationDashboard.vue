<script setup lang="ts">
import {
  CircleCheck,
  DataAnalysis,
  Document,
  MagicStick,
  Refresh,
  Timer,
  Warning,
} from "@element-plus/icons-vue"
import { computed, defineAsyncComponent, onMounted, ref, watch } from "vue"

import { getEvaluationRun, getEvaluationRuns } from "../api"
import { demoEvaluationRun } from "../demoData"
import type {
  EvaluationBranch,
  EvaluationRun,
  EvaluationRunSummary,
} from "../types"

const EvaluationMetricsChart = defineAsyncComponent(
  () => import("./EvaluationMetricsChart.vue"),
)
const props = defineProps<{ demo?: boolean }>()
const branchOrder: EvaluationBranch[] = ["sql", "rag", "hybrid"]
const failureFilters: ("all" | EvaluationBranch)[] = ["all", ...branchOrder]
const branchMeta = {
  sql: { label: "SQL", title: "经营数据", icon: DataAnalysis },
  rag: { label: "RAG", title: "制度问答", icon: Document },
  hybrid: { label: "HYBRID", title: "综合分析", icon: MagicStick },
}

const runs = ref<EvaluationRunSummary[]>([])
const selectedRunId = ref("")
const comparisonRunId = ref("")
const selectedRun = ref<EvaluationRun | null>(null)
const loading = ref(true)
const detailLoading = ref(false)
const error = ref("")
const failureFilter = ref<"all" | EvaluationBranch>("all")

const comparisonRun = computed(
  () => runs.value.find((run) => run.run_id === comparisonRunId.value) ?? null,
)
const filteredFailures = computed(() => {
  const failures = selectedRun.value?.failures ?? []
  return failureFilter.value === "all"
    ? failures
    : failures.filter((failure) => failure.branch === failureFilter.value)
})
const qualityCategories = computed(() =>
  Object.entries(selectedRun.value?.quality_gate?.categories ?? {}),
)
const challengeCategories = computed(() =>
  Object.entries(selectedRun.value?.evaluation_sets?.challenge?.categories ?? {}),
)

function percent(value: number | null | undefined): string {
  return value == null ? "--" : `${(value * 100).toFixed(1)}%`
}

function number(value: number | null | undefined): string {
  return value == null ? "--" : value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
}

function latency(value: number | null | undefined): string {
  if (value == null) return "--"
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${value.toFixed(0)}ms`
}

function dateTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function json(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2)
}

function accuracyDelta(branch: EvaluationBranch): number | null {
  if (!selectedRun.value || !comparisonRun.value) return null
  return (
    selectedRun.value.branches[branch].accuracy -
    comparisonRun.value.branches[branch].accuracy
  )
}

function deltaLabel(value: number | null): string {
  if (value == null) return "无对比批次"
  if (value === 0) return "与对比批次持平"
  return `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)} 个百分点`
}

async function loadSelectedRun(): Promise<void> {
  if (props.demo) {
    selectedRun.value = demoEvaluationRun
    return
  }
  if (!selectedRunId.value) {
    selectedRun.value = null
    return
  }
  detailLoading.value = true
  error.value = ""
  try {
    selectedRun.value = await getEvaluationRun(selectedRunId.value)
  } catch (reason) {
    selectedRun.value = null
    error.value = reason instanceof Error ? reason.message : "评测详情读取失败。"
  } finally {
    detailLoading.value = false
  }
}

async function refresh(): Promise<void> {
  loading.value = true
  error.value = ""
  try {
    if (props.demo) {
      runs.value = [demoEvaluationRun]
      selectedRunId.value = demoEvaluationRun.run_id
      comparisonRunId.value = ""
      selectedRun.value = demoEvaluationRun
      return
    }
    const response = await getEvaluationRuns()
    runs.value = response.runs
    if (!runs.value.some((run) => run.run_id === selectedRunId.value)) {
      selectedRunId.value = runs.value[0]?.run_id ?? ""
    }
    const comparisons = runs.value.filter((run) => run.run_id !== selectedRunId.value)
    if (!comparisons.some((run) => run.run_id === comparisonRunId.value)) {
      comparisonRunId.value = comparisons[0]?.run_id ?? ""
    }
    await loadSelectedRun()
  } catch (reason) {
    runs.value = []
    selectedRun.value = null
    error.value = reason instanceof Error ? reason.message : "评测批次读取失败。"
  } finally {
    loading.value = false
  }
}

watch(selectedRunId, async () => {
  if (!loading.value) {
    if (comparisonRunId.value === selectedRunId.value) comparisonRunId.value = ""
    await loadSelectedRun()
  }
})

watch(() => props.demo, refresh)

onMounted(refresh)
</script>

<template>
  <div class="evaluation-dashboard">
    <section class="evaluation-heading-band">
      <div>
        <span class="section-kicker">QUALITY EVIDENCE</span>
        <h1>评测结果</h1>
        <p v-if="selectedRun">
          {{ selectedRun.model }} · 数据集 {{ selectedRun.dataset_version }} ·
          {{ selectedRun.workspace_state === "clean" ? "干净工作区" : "含未提交改动" }}
        </p>
      </div>
      <div class="evaluation-controls">
        <label>
          <span>当前批次</span>
          <select v-model="selectedRunId" :disabled="loading || !runs.length">
            <option v-for="run in runs" :key="run.run_id" :value="run.run_id">
              {{ run.label }}
            </option>
          </select>
        </label>
        <label>
          <span>对比批次</span>
          <select v-model="comparisonRunId" :disabled="runs.length < 2">
            <option value="">不对比</option>
            <option
              v-for="run in runs.filter((item) => item.run_id !== selectedRunId)"
              :key="run.run_id"
              :value="run.run_id"
            >
              {{ run.label }}
            </option>
          </select>
        </label>
        <button class="evaluation-refresh" type="button" title="刷新评测批次" @click="refresh">
          <Refresh />
        </button>
      </div>
    </section>

    <div v-if="loading || detailLoading" class="evaluation-state" role="status">
      <span class="drawer-spinner" />
      <strong>正在读取评测批次</strong>
    </div>
    <div v-else-if="error" class="evaluation-state evaluation-error">
      <Warning />
      <strong>评测结果暂时不可用</strong>
      <p>{{ error }}</p>
      <button type="button" @click="refresh">重新读取</button>
    </div>
    <div v-else-if="!selectedRun" class="evaluation-state">
      <DataAnalysis />
      <strong>暂无评测批次</strong>
      <p>运行归档脚本后，批次会显示在这里。</p>
    </div>

    <template v-else>
      <section class="quality-gate-band">
        <div>
          <span>LOCAL QUALITY GATE</span>
          <strong v-if="selectedRun.quality_gate">
            {{ selectedRun.quality_gate.passed }}/{{ selectedRun.quality_gate.total }}
          </strong>
          <strong v-else>--</strong>
        </div>
        <div class="quality-gate-categories">
          <span v-for="[name, item] in qualityCategories" :key="name">
            {{ name }} <strong>{{ item.passed }}/{{ item.total }}</strong>
          </span>
        </div>
        <small>本地门禁不计入端到端模型准确率</small>
      </section>

      <section v-if="selectedRun.evaluation_sets" class="evaluation-section evaluation-set-section">
        <div class="evaluation-section-heading">
          <div>
            <span class="section-kicker">DATASET SCOPE</span>
            <h2>正常集、挑战集与已知限制</h2>
          </div>
          <span>挑战集不改变主分支准确率</span>
        </div>
        <div class="evaluation-set-grid">
          <article class="evaluation-set-summary">
            <span class="evaluation-set-label">NORMAL SET</span>
            <strong>
              {{ selectedRun.evaluation_sets.normal?.passed ?? selectedRun.total_passed }}/{{
                selectedRun.evaluation_sets.normal?.total ?? selectedRun.total_cases
              }}
            </strong>
            <b>{{ percent(selectedRun.evaluation_sets.normal?.accuracy ?? selectedRun.overall_accuracy) }}</b>
            <p>{{ selectedRun.evaluation_sets.normal?.description || "正常业务端到端样本。" }}</p>
          </article>
          <article class="evaluation-set-summary challenge">
            <span class="evaluation-set-label">CHALLENGE SET</span>
            <strong v-if="selectedRun.evaluation_sets.challenge">
              {{ selectedRun.evaluation_sets.challenge.passed }}/{{ selectedRun.evaluation_sets.challenge.total }}
            </strong>
            <strong v-else>--</strong>
            <b>{{ percent(selectedRun.evaluation_sets.challenge?.accuracy) }}</b>
            <div class="evaluation-set-categories">
              <span v-for="[name, item] in challengeCategories" :key="name">
                {{ name }} <strong>{{ item.passed }}/{{ item.total }}</strong>
              </span>
            </div>
            <p>{{ selectedRun.evaluation_sets.challenge?.description || "尚未运行挑战集。" }}</p>
          </article>
          <article class="evaluation-set-summary limitations">
            <span class="evaluation-set-label">KNOWN LIMITATIONS</span>
            <strong>{{ selectedRun.known_limitations?.length ?? 0 }}</strong>
            <b>待补强项</b>
            <ul>
              <li v-for="item in selectedRun.known_limitations" :key="item.id">{{ item.title }}</li>
            </ul>
          </article>
        </div>
      </section>

      <section class="evaluation-branch-grid" aria-label="分支评测指标">
        <article v-for="branch in branchOrder" :key="branch" class="evaluation-branch-card">
          <header>
            <span class="evaluation-branch-icon"><component :is="branchMeta[branch].icon" /></span>
            <div>
              <span>{{ branchMeta[branch].label }}</span>
              <h2>{{ branchMeta[branch].title }}</h2>
            </div>
            <strong>{{ selectedRun.branches[branch].passed }}/{{ selectedRun.branches[branch].total }}</strong>
          </header>
          <div class="branch-accuracy">
            <strong>{{ percent(selectedRun.branches[branch].accuracy) }}</strong>
            <span :class="{ positive: (accuracyDelta(branch) ?? 0) > 0, negative: (accuracyDelta(branch) ?? 0) < 0 }">
              {{ deltaLabel(accuracyDelta(branch)) }}
            </span>
          </div>
          <dl>
            <div><dt>拒答率</dt><dd>{{ percent(selectedRun.branches[branch].rejection_rate) }}</dd></div>
            <div><dt>总 Token</dt><dd>{{ number(selectedRun.branches[branch].total_tokens) }}</dd></div>
            <div><dt>平均 Token</dt><dd>{{ number(selectedRun.branches[branch].avg_tokens) }}</dd></div>
            <div><dt>P50</dt><dd>{{ latency(selectedRun.branches[branch].p50_latency_ms) }}</dd></div>
            <div><dt>P95</dt><dd>{{ latency(selectedRun.branches[branch].p95_latency_ms) }}</dd></div>
          </dl>
          <p>{{ selectedRun.branches[branch].coverage }}</p>
        </article>
      </section>

      <section class="evaluation-section evaluation-chart-section">
        <div class="evaluation-section-heading">
          <div>
            <span class="section-kicker">BRANCH COMPARISON</span>
            <h2>准确率与拒答率</h2>
          </div>
          <span>{{ selectedRun.total_passed }}/{{ selectedRun.total_cases }} 端到端样本通过</span>
        </div>
        <EvaluationMetricsChart
          :current="selectedRun.branches"
          :comparison="comparisonRun?.branches"
        />
      </section>

      <section class="evaluation-section">
        <div class="evaluation-section-heading">
          <div>
            <span class="section-kicker">FAILURE ANALYSIS</span>
            <h2>失败样本</h2>
          </div>
          <div class="failure-filter" aria-label="失败样本筛选">
            <button
              v-for="filter in failureFilters"
              :key="filter"
              type="button"
              :class="{ active: failureFilter === filter }"
              @click="failureFilter = filter"
            >
              {{ filter === "all" ? "全部" : branchMeta[filter].label }}
            </button>
          </div>
        </div>
        <div v-if="filteredFailures.length" class="failure-list">
          <article v-for="failure in filteredFailures" :key="failure.case_id" class="failure-item">
            <div class="failure-main">
              <span>{{ branchMeta[failure.branch].label }}</span>
              <div>
                <strong>{{ failure.case_id }} · {{ failure.diagnosis }}</strong>
                <p>{{ failure.question }}</p>
              </div>
              <small>{{ failure.set_type === "challenge" ? "挑战集" : "正常集" }} · {{ failure.failure_type }}</small>
            </div>
            <details>
              <summary>查看期望与实际结果</summary>
              <div class="failure-details">
                <div><span>期望</span><pre>{{ json(failure.expected) }}</pre></div>
                <div><span>实际</span><pre>{{ json(failure.actual) }}</pre></div>
              </div>
              <code v-if="failure.generated_sql">{{ failure.generated_sql }}</code>
              <p v-if="failure.errors.length">{{ failure.errors.join(" · ") }}</p>
            </details>
          </article>
        </div>
        <div v-else class="evaluation-empty">
          <CircleCheck />
          <strong>本批次没有失败样本</strong>
          <span>失败分析逻辑已启用，后续失败会按固定规则归类。</span>
        </div>
      </section>

      <section class="evaluation-section">
        <div class="evaluation-section-heading">
          <div>
            <span class="section-kicker">RUN HISTORY</span>
            <h2>历史批次</h2>
          </div>
          <span>{{ runs.length }} 个不可覆盖批次</span>
        </div>
        <div class="evaluation-table-wrap">
          <table class="evaluation-history-table">
            <thead>
              <tr>
                <th>批次</th><th>总准确率</th><th>SQL</th><th>RAG</th><th>Hybrid</th><th>样本</th><th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.run_id" :class="{ selected: run.run_id === selectedRunId }">
                <td><strong>{{ run.label }}</strong><small>{{ run.run_id }}</small></td>
                <td>{{ percent(run.overall_accuracy) }}</td>
                <td>{{ percent(run.branches.sql.accuracy) }}</td>
                <td>{{ percent(run.branches.rag.accuracy) }}</td>
                <td>{{ percent(run.branches.hybrid.accuracy) }}</td>
                <td>{{ run.total_passed }}/{{ run.total_cases }}</td>
                <td>{{ dateTime(run.generated_at) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="evaluation-footnotes">
        <div><Timer /><span>生成时间 {{ dateTime(selectedRun.generated_at) }}</span></div>
        <div><DataAnalysis /><span>Git {{ selectedRun.git_commit || "unknown" }}</span></div>
        <p v-for="note in selectedRun.notes" :key="note">{{ note }}</p>
      </section>
    </template>
  </div>
</template>
