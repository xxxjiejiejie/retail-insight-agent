<script setup lang="ts">
import { BarChart } from "echarts/charts"
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components"
import * as echarts from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { EvaluationBranch, EvaluationBranchMetrics } from "../types"

echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const props = defineProps<{
  current: Record<EvaluationBranch, EvaluationBranchMetrics>
  comparison?: Record<EvaluationBranch, EvaluationBranchMetrics> | null
}>()

const element = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null
const branches: EvaluationBranch[] = ["sql", "rag", "hybrid"]

function percentage(value: number): number {
  return Math.round(value * 1000) / 10
}

async function render(): Promise<void> {
  if (!element.value) return
  await nextTick()
  chart?.dispose()
  chart = echarts.init(element.value)
  const series: Record<string, unknown>[] = [
    {
      name: "当前准确率",
      type: "bar",
      data: branches.map((branch) => percentage(props.current[branch].accuracy)),
      barMaxWidth: 34,
      itemStyle: { color: "#168269", borderRadius: [5, 5, 1, 1] },
    },
    {
      name: "当前拒答率",
      type: "bar",
      data: branches.map((branch) => percentage(props.current[branch].rejection_rate)),
      barMaxWidth: 34,
      itemStyle: { color: "#d59b51", borderRadius: [5, 5, 1, 1] },
    },
  ]
  if (props.comparison) {
    series.splice(1, 0, {
      name: "对比准确率",
      type: "bar",
      data: branches.map((branch) => percentage(props.comparison![branch].accuracy)),
      barMaxWidth: 34,
      itemStyle: { color: "#91b9ad", borderRadius: [5, 5, 1, 1] },
    })
  }
  chart.setOption({
    animationDuration: 350,
    textStyle: {
      color: "#52645f",
      fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
    },
    grid: { left: 18, right: 16, top: 52, bottom: 18, containLabel: true },
    legend: { top: 6, right: 4, icon: "circle", itemWidth: 8, itemHeight: 8 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) => `${value}%`,
      borderWidth: 0,
      backgroundColor: "#142c27",
      textStyle: { color: "#fff" },
    },
    xAxis: {
      type: "category",
      data: ["SQL", "RAG", "Hybrid"],
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#dfe7e4" } },
      axisLabel: { color: "#52645f", fontWeight: 700 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { color: "#71837d", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "#e9efed", type: "dashed" } },
    },
    series,
  })
}

watch(() => [props.current, props.comparison], render, { deep: true })

onMounted(() => {
  render()
  if (element.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(element.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div ref="element" class="evaluation-chart" aria-label="各分支准确率与拒答率图表" />
</template>
