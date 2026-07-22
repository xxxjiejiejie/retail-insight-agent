<script setup lang="ts">
import * as echarts from "echarts"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

import type { ChartSpec, SQLResult } from "../types"

const props = defineProps<{
  spec?: ChartSpec | null
  result?: SQLResult | null
}>()

const chartElement = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null

const rows = computed<Record<string, unknown>[]>(() => {
  return props.result?.rows ?? []
})

async function renderChart(): Promise<void> {
  if (!props.spec || rows.value.length === 0 || !chartElement.value) return
  await nextTick()
  chart?.dispose()
  chart = echarts.init(chartElement.value)
  const xData = rows.value.map((row) => row[props.spec!.x_field])
  const yData = rows.value.map((row) => row[props.spec!.y_field])
  if (props.spec.type === "pie") {
    chart.setOption({
      title: { text: props.spec.title },
      tooltip: { trigger: "item" },
      series: [
        {
          type: "pie",
          radius: "60%",
          data: xData.map((name, index) => ({ name, value: yData[index] })),
        },
      ],
    })
  } else {
    chart.setOption({
      title: { text: props.spec.title },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: xData },
      yAxis: { type: "value" },
      series: [{ type: props.spec.type, data: yData }],
    })
  }
}

watch(() => [props.spec, props.result], renderChart, { deep: true })
onMounted(renderChart)
onBeforeUnmount(() => chart?.dispose())
</script>

<template>
  <div v-if="spec && rows.length" ref="chartElement" class="chart-panel" />
</template>
