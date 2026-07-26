import { expect, test } from "@playwright/test"

const branch = (accuracy: number, total = 5) => ({
  passed: Math.round(accuracy * total),
  total,
  accuracy,
  rejected: 0,
  rejection_rate: 0,
  total_tokens: 500,
  avg_tokens: 100,
  p50_latency_ms: 1000,
  p95_latency_ms: 2000,
  coverage: "E2E 固定样本",
})

const currentRun = {
  run_id: "run-current",
  label: "当前测试批次",
  generated_at: "2026-07-24T08:00:00+00:00",
  model: "test-model",
  dataset_version: "dataset-current",
  git_commit: "abc1234",
  workspace_state: "clean",
  total_cases: 15,
  total_passed: 12,
  overall_accuracy: 0.8,
  branches: { sql: branch(0.8), rag: branch(0.8), hybrid: branch(0.8) },
  quality_gate: {
    passed: 99,
    total: 100,
    accuracy: 0.99,
    duration_ms: 1200,
    categories: { router: { passed: 24, total: 25, pass_rate: 0.96 } },
  },
}

const previousRun = {
  ...currentRun,
  run_id: "run-previous",
  label: "上一测试批次",
  generated_at: "2026-07-23T08:00:00+00:00",
  total_passed: 9,
  overall_accuracy: 0.6,
  branches: { sql: branch(0.6), rag: branch(0.6), hybrid: branch(0.6) },
}

test("shows the expanded archived real batch", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: /评测结果/ }).click()

  await expect(page.getByRole("heading", { name: "评测结果" })).toBeVisible()
  await expect(page.getByLabel("当前批次")).toHaveValue("v10-deterministic-fixes-20260726")
  await expect(page.getByText("52/55 端到端样本通过", { exact: true })).toBeVisible()
  await expect(page.getByText("100/100", { exact: true })).toBeVisible()
  await expect(page.getByText("正常集、挑战集与已知限制", { exact: true })).toBeVisible()
  await expect(page.getByText("10/12", { exact: true })).toBeVisible()
  await expect(page.getByText(/SQL-SMOKE-026/)).toBeVisible()
  await expect(page.locator("article.evaluation-branch-card")).toHaveCount(3)
  await expect.poll(() =>
    page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBe(true)
})

test("compares batches and expands deterministic failure analysis", async ({ page }) => {
  await page.route("**/api/v1/evaluation/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith("/evaluation/runs")) {
      await route.fulfill({ json: { runs: [currentRun, previousRun] } })
      return
    }
    const run = pathname.endsWith("run-current") ? currentRun : previousRun
    await route.fulfill({
      json: {
        ...run,
        failures:
          run.run_id === "run-current"
            ? [
                {
                  case_id: "SQL-FAIL-001",
                  branch: "sql",
                  failure_type: "row_count_mismatch",
                  diagnosis: "生成结果行数与参考结果不一致。",
                  question: "失败问题",
                  expected: { row_count: 2 },
                  actual: { row_count: 1 },
                  errors: [],
                  generated_sql: "SELECT 1",
                  total_tokens: 100,
                  latency_ms: 1000,
                },
              ]
            : [],
        source_reports: ["fixture.json"],
        notes: ["E2E 固定数据。"],
      },
    })
  })

  await page.goto("/")
  await page.getByRole("button", { name: /评测结果/ }).click()

  await expect(page.getByLabel("对比批次")).toHaveValue("run-previous")
  const sqlCard = page.locator("article.evaluation-branch-card").filter({ hasText: "经营数据" })
  await expect(sqlCard.getByText("+20.0 个百分点", { exact: true })).toBeVisible()
  await expect(page.getByText(/SQL-FAIL-001/)).toBeVisible()
  await page.getByText("查看期望与实际结果", { exact: true }).click()
  await expect(page.getByText(/"row_count": 2/)).toBeVisible()
  await expect(page.locator(".evaluation-history-table tbody tr")).toHaveCount(2)
})

test("demo evaluation uses embedded data without API calls", async ({ page }) => {
  await page.route("**/api/v1/evaluation/**", async (route) => {
    await route.abort()
  })
  await page.goto("/?demo=1")
  await page.getByRole("button", { name: /评测结果/ }).click()

  await expect(page.getByLabel("当前批次")).toHaveValue("demo-evaluation")
  await expect(page.getByText("演示模式不读取真实评测报告，不调用模型，不消耗 Token。", { exact: true })).toBeVisible()
})
