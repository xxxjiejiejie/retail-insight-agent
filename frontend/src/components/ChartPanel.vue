<script setup lang="ts">
import { BarChart, LineChart, PieChart, ScatterChart } from "echarts/charts"
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components"
import * as echarts from "echarts/core"
import { CanvasRenderer } from "echarts/renderers"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { ChartSpec, SQLResult } from "../types"

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

const props = defineProps<{
  spec?: ChartSpec | null
  result?: SQLResult | null
}>()

const chartElement = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

const rows = computed<Record<string, unknown>[]>(() => props.result?.rows ?? [])

function numericValue(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

async function renderChart(): Promise<void> {
  if (!props.spec || rows.value.length === 0 || !chartElement.value) return
  await nextTick()
  chart?.dispose()
  chart = echarts.init(chartElement.value)
  const xData = rows.value.map((row) => String(row[props.spec!.x_field] ?? "—"))
  const yData = rows.value.map((row) => numericValue(row[props.spec!.y_field]))
  const commonTextStyle = {
    color: "#52645f",
    fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif',
  }

  if (props.spec.type === "pie") {
    chart.setOption({
      color: ["#1a7f64", "#77b39e", "#e6a85c", "#556f78", "#b9d8cc"],
      textStyle: commonTextStyle,
      tooltip: {
        trigger: "item",
        borderWidth: 0,
        backgroundColor: "#142c27",
        textStyle: { color: "#fff" },
      },
      legend: {
        bottom: 0,
        icon: "circle",
        textStyle: commonTextStyle,
      },
      series: [
        {
          type: "pie",
          radius: ["42%", "68%"],
          center: ["50%", "44%"],
          padAngle: 3,
          itemStyle: { borderRadius: 8 },
          label: { color: "#52645f", formatter: "{b}\n{d}%" },
          data: xData.map((name, index) => ({ name, value: yData[index] })),
        },
      ],
    })
  } else if (props.spec.type === "scatter") {
    chart.setOption({
      color: ["#168269"],
      textStyle: commonTextStyle,
      grid: { left: 18, right: 18, top: 28, bottom: 18, containLabel: true },
      tooltip: {
        trigger: "item",
        borderWidth: 0,
        backgroundColor: "#142c27",
        textStyle: { color: "#fff" },
        formatter: (params: { value?: unknown[] }) => {
          const [xValue, yValue] = params.value ?? []
          return `${props.spec!.x_field}: ${xValue ?? "—"}<br/>${props.spec!.y_field}: ${yValue ?? "—"}`
        },
      },
      xAxis: {
        type: "value",
        name: props.spec.x_field,
        nameLocation: "middle",
        nameGap: 30,
        axisLine: { lineStyle: { color: "#dfe7e4" } },
        splitLine: { lineStyle: { color: "#edf2f0", type: "dashed" } },
        axisLabel: { color: "#667a74" },
      },
      yAxis: {
        type: "value",
        name: props.spec.y_field,
        nameLocation: "middle",
        nameGap: 54,
        splitLine: { lineStyle: { color: "#edf2f0", type: "dashed" } },
        axisLabel: { color: "#667a74" },
      },
      series: [
        {
          type: "scatter",
          data: rows.value.map((row) => [
            numericValue(row[props.spec!.x_field]),
            numericValue(row[props.spec!.y_field]),
          ]),
          symbolSize: 12,
          itemStyle: { color: "#168269", opacity: 0.82 },
        },
      ],
    })
  } else {
    chart.setOption({
      color: ["#168269"],
      textStyle: commonTextStyle,
      grid: { left: 18, right: 18, top: 24, bottom: 18, containLabel: true },
      tooltip: {
        trigger: "axis",
        borderWidth: 0,
        backgroundColor: "#142c27",
        textStyle: { color: "#fff" },
        axisPointer: { type: "shadow", shadowStyle: { color: "rgba(22,130,105,.08)" } },
      },
      xAxis: {
        type: "category",
        data: xData,
        axisLine: { lineStyle: { color: "#dfe7e4" } },
        axisTick: { show: false },
        axisLabel: { color: "#667a74", interval: 0, rotate: xData.length > 8 ? 24 : 0 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#edf2f0", type: "dashed" } },
        axisLabel: { color: "#667a74" },
      },
      series: [
        {
          type: props.spec.type,
          data: yData,
          smooth: props.spec.type === "line",
          symbolSize: 8,
          lineStyle: { width: 3 },
          areaStyle:
            props.spec.type === "line" ? { color: "rgba(22,130,105,.08)" } : undefined,
          itemStyle:
            props.spec.type === "bar"
              ? { borderRadius: [7, 7, 2, 2], color: "#168269" }
              : { color: "#168269" },
          barMaxWidth: 48,
        },
      ],
    })
  }
}

watch(() => [props.spec, props.result], renderChart, { deep: true })

onMounted(() => {
  renderChart()
  if (chartElement.value) {
    resizeObserver = new ResizeObserver(() => chart?.resize())
    resizeObserver.observe(chartElement.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
})
</script>

<template>
  <div v-if="spec && rows.length" ref="chartElement" class="chart-panel" />
  <div v-else class="chart-empty">
    <span>当前结果不适合生成图表，明细数据仍可正常查看。</span>
  </div>
</template>
