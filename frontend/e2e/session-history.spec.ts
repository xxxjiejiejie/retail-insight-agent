import { expect, test } from "@playwright/test"

const persistedTurns = Array.from({ length: 8 }, (_, index) => ({
  turn_id: `turn-e2e-${String(index + 1).padStart(3, "0")}`,
  created_at: `2026-07-24T${String(index + 8).padStart(2, "0")}:00:00+00:00`,
  query: `历史会话问题 ${index + 1}`,
  resolved_query: null,
  context_used: false,
  intent: "sql",
  answer: `历史回答 ${index + 1}`,
  clarification: null,
  generated_sql: "SELECT 1",
  sql_result: null,
  chart_spec: null,
  citations: [],
  errors: [],
  metrics: {},
}))

test("new session keeps recent history after reload", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "移动端按设计隐藏最近会话栏")
  await page.addInitScript(() => {
    localStorage.setItem("retail-insight-session-id", "session-e2e-old")
    localStorage.setItem("retail-insight-session-index", JSON.stringify(["session-e2e-old"]))
  })
  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith("/health")) {
      await route.fulfill({ json: { status: "ok", app: "test", environment: "e2e" } })
    } else if (pathname.endsWith("/metadata/schema")) {
      await route.fulfill({ json: { tables: [] } })
    } else if (pathname.endsWith("/metadata/policies")) {
      await route.fulfill({ json: { documents: [] } })
    } else if (pathname.includes("/sessions/")) {
      const isOld = pathname.endsWith("session-e2e-old")
      await route.fulfill({
        json: { session_id: pathname.split("/").pop(), turns: isOld ? persistedTurns : [] },
      })
    } else if (pathname.endsWith("/evaluation/runs")) {
      await route.fulfill({ json: { runs: [] } })
    } else {
      await route.fulfill({ status: 404, json: { detail: "not found" } })
    }
  })

  await page.goto("/")
  await expect(page.getByRole("button", { name: /历史会话问题 8/ })).toBeVisible()
  await expect(page.locator(".recent-list")).toHaveCSS("overflow-y", "auto")
  await page.getByRole("button", { name: "新建会话" }).click()
  await expect(page.getByRole("button", { name: /历史会话问题 1/ })).toBeAttached()
  await page.reload()
  await expect(page.getByRole("button", { name: /历史会话问题 1/ })).toBeAttached()
})
