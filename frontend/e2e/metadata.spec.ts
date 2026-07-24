import { expect, test } from "@playwright/test"

test("expands and scrolls the complete database schema", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: /经营数据库/ }).click()

  const tables = page.locator("details.schema-table")
  await expect(tables).toHaveCount(8)
  for (let index = 0; index < 8; index += 1) {
    const table = tables.nth(index)
    if (!(await table.evaluate((element) => (element as HTMLDetailsElement).open))) {
      await table.locator("summary").click()
    }
  }
  await expect.poll(() =>
    page.locator(".metadata-list").evaluate((element) => element.scrollHeight > element.clientHeight),
  ).toBe(true)
})

test("opens a policy document and returns to the catalog", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("button", { name: /制度知识库/ }).click()
  await page.locator("button.policy-card").filter({ hasText: "商品退换货处理规范" }).click()

  await expect(page.getByRole("heading", { name: "商品退换货处理规范" })).toBeVisible()
  await expect(page.getByRole("heading", { name: "受理条件" })).toBeVisible()
  await page.getByRole("button", { name: "返回制度目录" }).click()
  await expect(page.locator("button.policy-card")).toHaveCount(8)
  await expect.poll(() =>
    page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
  ).toBe(true)
})
