import { expect, test } from "@playwright/test";

test.skip(process.env.NEXT_PUBLIC_USE_MOCKS !== "false", "real API coverage requires NEXT_PUBLIC_USE_MOCKS=false");

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:4010/api/v1";
const timestamp = "2026-05-22T10:00:00Z";

test("loads and deletes existing identity rules through real API routes", async ({ page }) => {
  const identityRequests: string[] = [];
  const deleteRequests: string[] = [];
  let wbRules = [
    {
      id: "identity_wb_block_001",
      platformId: "wb",
      listType: "block",
      userId: "blocked_existing_001",
      label: "既有屏蔽用户",
      createdAt: timestamp
    },
    {
      id: "identity_wb_allow_001",
      platformId: "wb",
      listType: "allow",
      userId: "allowed_existing_002",
      label: "既有白名单用户",
      createdAt: timestamp
    }
  ];

  await routeJson(page, "/system/components", {
    success: true,
    components: [
      { id: "query", name: "Query Engine", status: "running", port: 9001, lastHeartbeatAt: timestamp },
      { id: "media", name: "Media Engine", status: "running", port: 9002, lastHeartbeatAt: timestamp },
      { id: "insight", name: "Insight Engine", status: "degraded", port: 9003, lastHeartbeatAt: timestamp },
      { id: "report", name: "Report Engine", status: "running" },
      { id: "mindspider", name: "MindSpider", status: "running" }
    ]
  });
  await routeJson(page, "/report-templates", {
    success: true,
    templates: [{ id: "daily-monitoring", name: "日报", filename: "daily.md", description: "", sizeBytes: 10 }]
  });
  await routeJson(page, "/report-tasks", { success: true, tasks: [] });
  await routeJson(page, "/crawler-tasks", { success: true, tasks: [] });
  await routeJson(page, "/crawler-strategies", {
    success: true,
    strategies: [
      {
        id: "strategy_daily",
        workspaceId: "workspace_e2e",
        name: "每日采集",
        runMode: "deep_sentiment",
        platformPolicies: [],
        createdAt: timestamp,
        updatedAt: timestamp
      }
    ]
  });
  await routeJson(page, "/platforms", {
    success: true,
    platforms: [
      platform("wb", "微博", { allow: 1, block: 1 }),
      platform("xhs", "小红书", { allow: 0, block: 0 })
    ]
  });
  await routeJson(page, "/system/config", {
    success: true,
    fields: [
      {
        key: "REPORT_ENGINE_API_KEY",
        label: "Report API Key",
        group: "llm",
        type: "secret",
        value: "********",
        editable: true,
        sensitive: true
      }
    ]
  });
  await routeJson(page, "/logs?tail=300", { success: true, lines: [] });

  await page.route(`${apiBase}/platforms/*/identity-lists`, async (route) => {
    const requestUrl = new URL(route.request().url());
    const parts = requestUrl.pathname.split("/");
    const platformId = parts[parts.indexOf("platforms") + 1];
    identityRequests.push(platformId);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        rules: platformId === "wb" ? wbRules : []
      })
    });
  });
  await page.route(`${apiBase}/platforms/wb/identity-lists/identity_wb_block_001`, async (route) => {
    expect(route.request().method()).toBe("DELETE");
    deleteRequests.push(route.request().url());
    wbRules = wbRules.filter((rule) => rule.id !== "identity_wb_block_001");
    await route.fulfill({ status: 204 });
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("API connected")).toBeVisible();
  await expect(page.getByText("Query Engine")).toBeVisible();
  await expect(page.getByText(/:900[123]/)).toHaveCount(0);
  await page.getByRole("button", { name: "平台规则" }).click();

  expect(identityRequests).toEqual(["wb", "xhs"]);
  await expect(page.getByText("blocked_existing_001")).toBeVisible();
  await expect(page.getByText("既有屏蔽用户")).toBeVisible();
  await expect(page.getByText("allowed_existing_002")).toBeVisible();

  await page.locator(".rule-row", { hasText: "blocked_existing_001" }).getByTitle("删除名单规则").click();
  await expect(page.getByText("名单规则已删除")).toBeVisible();
  await expect(page.getByText("blocked_existing_001")).toHaveCount(0);
  expect(deleteRequests).toHaveLength(1);
});

async function routeJson(page: import("@playwright/test").Page, path: string, body: unknown) {
  await page.route(`${apiBase}${path}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body)
    });
  });
}

function platform(
  id: "wb" | "xhs",
  name: string,
  identityRuleCounts: { allow: number; block: number }
) {
  return {
    id,
    name,
    enabled: true,
    crawlerType: "search",
    identityRuleCounts,
    policy: {
      platformId: id,
      enabled: true,
      crawlDepth: 3,
      maxKeywords: 100,
      maxNotesPerKeyword: 50,
      maxCommentsPerNote: 100,
      keywords: [],
      keywordSource: "manual",
      frequency: { mode: "manual", timezone: "Asia/Shanghai" },
      loginType: "qrcode",
      headless: true,
      updatedAt: timestamp
    }
  };
}
