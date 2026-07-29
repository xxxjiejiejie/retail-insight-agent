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
  RAGAblationPipeline,
} from "../types"

const EvaluationMetricsChart = defineAsyncComponent(
  () => import("./EvaluationMetricsChart.vue"),
)
const RAGAblationChart = defineAsyncComponent(
  () => import("./RAGAblationChart.vue"),
)
const props = defineProps<{ demo?: boolean }>()
const branchOrder: EvaluationBranch[] = ["sql", "rag", "hybrid"]
const ragPipelineOrder: RAGAblationPipeline[] = ["vector", "bm25", "rrf", "rrf_reranker"]
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
const multiTurnCategories = computed(() =>
  Object.entries(selectedRun.value?.evaluation_sets?.multi_turn?.categories ?? {}),
)
const resilienceCategories = computed(() =>
  Object.entries(selectedRun.value?.evaluation_sets?.resilience?.categories ?? {}),
)
const ragAblationFailures = computed(() =>
  (selectedRun.value?.rag_ablation?.failures ?? []).slice(0, 8),
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

function evaluationSetDelta(setName: string): number | null {
  const current = selectedRun.value?.evaluation_sets?.[setName]
  const previous = comparisonRun.value?.evaluation_sets?.[setName]
  if (!current || !previous) return null
  return current.accuracy - previous.accuracy
}

function evaluationSetResult(setName: string): string {
  const item = selectedRun.value?.evaluation_sets?.[setName]
  return item ? `${item.passed}/${item.total}` : "--"
}

function failureDeltaLabel(): string {
  if (!selectedRun.value || !comparisonRun.value) return "无对比批次"
  const current = selectedRun.value.failure_count ?? selectedRun.value.failures.length
  const previous = comparisonRun.value.failure_count
  if (previous == null) return `${current} 条真实失败`
  const delta = current - previous
  if (delta === 0) return `与对比批次同为 ${current} 条`
  return `${delta > 0 ? "+" : ""}${delta} 条，当前 ${current} 条`
}

function setTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    normal: "正常集",
    challenge: "挑战集",
    multi_turn: "多轮集",
    resilience: "故障集",
  }
  return labels[value] ?? value
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
            <h2>正常集、挑战集与专项证据</h2>
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
          <article v-if="selectedRun.evaluation_sets.multi_turn?.total" class="evaluation-set-summary multi-turn">
            <span class="evaluation-set-label">MULTI-TURN SET</span>
            <strong>
              {{ selectedRun.evaluation_sets.multi_turn.passed }}/{{ selectedRun.evaluation_sets.multi_turn.total }}
            </strong>
            <b>{{ percent(selectedRun.evaluation_sets.multi_turn.accuracy) }}</b>
            <div class="evaluation-set-categories">
              <span v-for="[name, item] in multiTurnCategories" :key="name">
                {{ name }} <strong>{{ item.passed }}/{{ item.total }}</strong>
              </span>
            </div>
            <p>{{ selectedRun.evaluation_sets.multi_turn.description }}</p>
          </article>
          <article v-if="selectedRun.evaluation_sets.resilience?.total" class="evaluation-set-summary resilience">
            <span class="evaluation-set-label">RESILIENCE SET</span>
            <strong>
              {{ selectedRun.evaluation_sets.resilience.passed }}/{{ selectedRun.evaluation_sets.resilience.total }}
            </strong>
            <b>{{ percent(selectedRun.evaluation_sets.resilience.accuracy) }}</b>
            <div class="evaluation-set-categories">
              <span v-for="[name, item] in resilienceCategories" :key="name">
                {{ name }} <strong>{{ item.passed }}/{{ item.total }}</strong>
              </span>
            </div>
            <p>{{ selectedRun.evaluation_sets.resilience.description }}</p>
          </article>
        </div>
      </section>

      <section v-if="selectedRun.rag_ablation" class="evaluation-section rag-ablation-section">
        <div class="evaluation-section-heading">
          <div>
            <span class="section-kicker">RAG RETRIEVAL ABLATION</span>
            <h2>RAG 检索消融实验</h2>
          </div>
          <span>只在 {{ selectedRun.rag_ablation.answerable_cases }} 条可回答问题上计算标准指标</span>
        </div>
        <div class="rag-ablation-scope">
          <article>
            <span>制度文档</span>
            <strong>{{ selectedRun.rag_ablation.corpus.document_count }}</strong>
            <small>{{ selectedRun.rag_ablation.corpus.domain_count }} 个业务域</small>
          </article>
          <article>
            <span>检索 Chunk</span>
            <strong>{{ selectedRun.rag_ablation.corpus.chunk_count }}</strong>
            <small>稳定 chunk_id</small>
          </article>
          <article>
            <span>评测问题</span>
            <strong>{{ selectedRun.rag_ablation.total_cases }}</strong>
            <small>{{ selectedRun.rag_ablation.negative_cases }} 条库外诊断题</small>
          </article>
          <article>
            <span>评测版本</span>
            <strong class="rag-version">{{ selectedRun.rag_ablation.dataset_version }}</strong>
            <small>Top-{{ selectedRun.rag_ablation.top_k }} chunk</small>
          </article>
        </div>
        <RAGAblationChart :pipelines="selectedRun.rag_ablation.pipelines" />
        <div class="rag-ablation-metrics-grid">
          <article
            v-for="pipeline in ragPipelineOrder"
            :key="pipeline"
            :class="{ highlight: pipeline === 'rrf_reranker' }"
          >
            <span>{{ selectedRun.rag_ablation.pipelines[pipeline].label }}</span>
            <strong>{{ percent(selectedRun.rag_ablation.pipelines[pipeline].hit_at_5) }}</strong>
            <dl>
              <div><dt>MRR@5</dt><dd>{{ percent(selectedRun.rag_ablation.pipelines[pipeline].mrr_at_5) }}</dd></div>
              <div><dt>nDCG@5</dt><dd>{{ percent(selectedRun.rag_ablation.pipelines[pipeline].ndcg_at_5) }}</dd></div>
              <div><dt>P50 / P95</dt><dd>{{ latency(selectedRun.rag_ablation.pipelines[pipeline].p50_latency_ms) }} / {{ latency(selectedRun.rag_ablation.pipelines[pipeline].p95_latency_ms) }}</dd></div>
              <div><dt>失败样本</dt><dd>{{ selectedRun.rag_ablation.pipelines[pipeline].failure_count }}</dd></div>
            </dl>
          </article>
        </div>
        <div v-if="ragAblationFailures.length" class="rag-ablation-failures">
          <div class="rag-ablation-failure-heading">
            <strong>失败样本（展示前 8 条）</strong>
            <span>共 {{ selectedRun.rag_ablation.failures.length }} 条 Pipeline 失败记录</span>
          </div>
          <article v-for="failure in ragAblationFailures" :key="`${failure.pipeline}-${failure.case_id}`">
            <span>{{ failure.pipeline }}</span>
            <div><strong>{{ failure.case_id }}</strong><p>{{ failure.question }}</p></div>
            <small>期望 {{ failure.expected_document_ids.join('、') || '无' }}<br />实际 {{ failure.retrieved_document_ids.join('、') || '无' }}</small>
          </article>
        </div>
        <p class="rag-ablation-note">
          库外问题不计入 Hit@5、MRR@5、nDCG@5；裸检索器的候选非空率只作诊断，不能替代端到端拒答率。
        </p>
      </section>

      <section
        v-if="selectedRun.improvements?.length || selectedRun.known_limitations?.length"
        class="evaluation-section evaluation-regression-section"
      >
        <div class="evaluation-section-heading">
          <div>
            <span class="section-kicker">OPTIMIZATION REGRESSION</span>
            <h2>优化说明、指标变化与剩余限制</h2>
          </div>
          <span>{{ comparisonRun ? `对比 ${comparisonRun.label}` : "选择历史批次查看变化" }}</span>
        </div>
        <div class="evaluation-delta-grid">
          <article>
            <span>正常集</span>
            <strong>{{ evaluationSetResult("normal") }}</strong>
            <small>{{ deltaLabel(evaluationSetDelta("normal")) }}</small>
          </article>
          <article>
            <span>挑战集</span>
            <strong>{{ evaluationSetResult("challenge") }}</strong>
            <small>{{ deltaLabel(evaluationSetDelta("challenge")) }}</small>
          </article>
          <article>
            <span>真实多轮</span>
            <strong>{{ evaluationSetResult("multi_turn") }}</strong>
            <small>{{ comparisonRun?.evaluation_sets?.multi_turn ? deltaLabel(evaluationSetDelta("multi_turn")) : "本批次新增证据" }}</small>
          </article>
          <article>
            <span>失败样本</span>
            <strong>{{ selectedRun.failure_count ?? selectedRun.failures.length }}</strong>
            <small>{{ failureDeltaLabel() }}</small>
          </article>
        </div>
        <div v-if="selectedRun.improvements?.length" class="evaluation-improvement-grid">
          <article v-for="item in selectedRun.improvements" :key="item.id">
            <span>{{ item.id }}</span>
            <h3>{{ item.title }}</h3>
            <dl>
              <div><dt>原问题</dt><dd>{{ item.problem }}</dd></div>
              <div><dt>本次改动</dt><dd>{{ item.change }}</dd></div>
              <div><dt>验证证据</dt><dd>{{ item.evidence }}</dd></div>
            </dl>
          </article>
        </div>
        <div v-if="selectedRun.known_limitations?.length" class="evaluation-limit-list">
          <article v-for="item in selectedRun.known_limitations" :key="item.id">
            <span>{{ item.id }}</span>
            <div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div>
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
              <small>{{ setTypeLabel(failure.set_type) }} · {{ failure.failure_type }}</small>
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
