import { expect, type Page, test } from "@playwright/test";

test.skip(process.env.NEXT_PUBLIC_USE_MOCKS === "false", "mock adapter coverage runs only in mock mode");

async function openConsole(page: Page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { name: "舆情 SaaS 控制台" })).toBeVisible();
}

test("opens every primary SaaS console section", async ({ page }) => {
  await openConsole(page);

  await expect(page.getByText("Mock adapter")).toBeVisible();
  await expect(page.getByRole("heading", { name: "运行总览" })).toBeVisible();
  await expect(page.getByText("Query Engine")).toBeVisible();
  await expect(page.getByText(":5432")).toHaveCount(0);

  for (const [nav, heading] of [
    ["报告", "报告任务"],
    ["爬虫", "爬虫任务"],
    ["平台规则", "平台策略"],
    ["系统配置", "系统配置"],
    ["运行日志", "运行日志"]
  ] as const) {
    await page.getByRole("button", { name: nav }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
});

test("validates and creates a report task", async ({ page }) => {
  await openConsole(page);
  await page.getByRole("button", { name: "报告" }).click();

  await page.getByRole("button", { name: "创建报告" }).click();
  await expect(page.getByText("报告主题不能为空")).toBeVisible();

  await page.getByPlaceholder("输入报告主题").fill("BET-5 前端报告任务");
  await page.getByRole("button", { name: "创建报告" }).click();

  await expect(page.getByText("报告任务已创建")).toBeVisible();
  await expect(page.getByText("BET-5 前端报告任务")).toBeVisible();
});

test("validates crawler platform selection and creates a crawler task", async ({ page }) => {
  await openConsole(page);
  await page.getByRole("button", { name: "爬虫" }).click();

  for (const platformName of ["微博", "小红书", "知乎"]) {
    await page.getByLabel(platformName).uncheck();
  }

  await page.getByRole("button", { name: "创建任务" }).click();
  await expect(page.getByText("至少选择一个平台")).toBeVisible();

  await page.getByLabel("微博").check();
  await page.getByRole("button", { name: "创建任务" }).click();
  await expect(page.getByText("爬虫任务已创建")).toBeVisible();
});

test("validates identity list input and adds a platform rule", async ({ page }) => {
  await openConsole(page);
  await page.getByRole("button", { name: "平台规则" }).click();

  await page.getByRole("button", { name: "添加" }).click();
  await expect(page.getByText("用户 ID 不能为空")).toBeVisible();

  await page.getByPlaceholder("平台用户 ID").fill("blocked_user_005");
  await page.getByPlaceholder("标签").fill("测试屏蔽用户");
  await page.getByRole("button", { name: "添加" }).click();

  await expect(page.getByText("名单规则已添加")).toBeVisible();
  await expect(page.getByText("blocked_user_005")).toBeVisible();
  await expect(page.getByText("测试屏蔽用户")).toBeVisible();
});

test("keeps sensitive system configuration fields masked in the UI", async ({ page }) => {
  await openConsole(page);
  await page.getByRole("button", { name: "系统配置" }).click();

  const reportApiKey = page.getByLabel("Report API Key");
  await expect(reportApiKey).toHaveAttribute("type", "password");
  await expect(reportApiKey).toHaveAttribute("placeholder", "********");
  await expect(reportApiKey).toHaveValue("");

  await reportApiKey.fill("sk-ui-secret");
  await page.getByRole("button", { name: "保存配置" }).click();
  await expect(page.getByText("系统配置已保存")).toBeVisible();
});
