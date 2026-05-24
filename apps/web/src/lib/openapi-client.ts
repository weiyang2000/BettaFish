"use client";

import {
  configFields,
  crawlerTasks,
  getMockSnapshot,
  identityRules,
  logs,
  platforms,
  reportTasks,
  WORKSPACE_ID
} from "./mock-data";
import type {
  ConfigField,
  ConsoleSnapshot,
  CreateCrawlerTaskInput,
  CreateReportTaskInput,
  CrawlerTask,
  IdentityRule,
  IdentityRuleInput,
  PlatformId,
  PlatformPolicy,
  ReportTask,
  SystemComponent
} from "./types";

export const OPENAPI_PATHS = {
  health: "/health",
  components: "/system/components",
  componentStart: (id: string) => `/system/components/${id}:start`,
  componentStop: (id: string) => `/system/components/${id}:stop`,
  systemConfig: "/system/config",
  logs: "/logs",
  reportTemplates: "/report-templates",
  reportTasks: "/report-tasks",
  reportTask: (id: string) => `/report-tasks/${id}`,
  reportTaskCancel: (id: string) => `/report-tasks/${id}:cancel`,
  reportTaskEvents: (id: string) => `/report-tasks/${id}/events`,
  crawlerStrategies: "/crawler-strategies",
  crawlerAccounts: "/crawler-accounts",
  crawlerTasks: "/crawler-tasks",
  crawlerTask: (id: string) => `/crawler-tasks/${id}`,
  crawlerTaskStop: (id: string) => `/crawler-tasks/${id}:stop`,
  crawlerTaskRetry: (id: string) => `/crawler-tasks/${id}:retry`,
  platforms: "/platforms",
  platformPolicy: (id: string) => `/platforms/${id}/policy`,
  platformIdentityRules: (id: string) => `/platforms/${id}/identity-lists`,
  platformIdentityRule: (platformId: string, ruleId: string) =>
    `/platforms/${platformId}/identity-lists/${ruleId}`
} as const;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "";
const USE_MOCKS =
  process.env.NEXT_PUBLIC_USE_MOCKS === "true" || process.env.NEXT_PUBLIC_API_BASE_URL === undefined;
const workspaceId = process.env.NEXT_PUBLIC_WORKSPACE_ID ?? WORKSPACE_ID;

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (USE_MOCKS || !API_BASE_URL) {
    throw new Error("Mock mode is active");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Id": workspaceId,
      ...(init.headers ?? {})
    }
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const message =
      body?.error?.message ?? body?.message ?? `Request failed with HTTP ${response.status}`;
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function taskTimestamp(): string {
  return new Date().toISOString();
}

function nextId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}`;
}

function addLog(source: "system" | "report" | "crawler", message: string, taskId?: string): void {
  logs.unshift({
    id: nextId("log"),
    source,
    level: "info",
    timestamp: taskTimestamp(),
    message,
    taskId
  });
}

export async function loadConsoleSnapshot(): Promise<ConsoleSnapshot> {
  if (USE_MOCKS || !API_BASE_URL) {
    return getMockSnapshot();
  }

  const [
    components,
    templates,
    reportTaskPage,
    crawlerTaskPage,
    strategies,
    accountPage,
    platformPage,
    config,
    logPage
  ] = await Promise.all([
    requestJson<{ components: SystemComponent[] }>(OPENAPI_PATHS.components),
    requestJson<{ templates: ConsoleSnapshot["reportTemplates"] }>(OPENAPI_PATHS.reportTemplates),
    requestJson<{ tasks: ReportTask[] }>(OPENAPI_PATHS.reportTasks),
    requestJson<{ tasks: CrawlerTask[] }>(OPENAPI_PATHS.crawlerTasks),
    requestJson<{ strategies: ConsoleSnapshot["crawlerStrategies"] }>(OPENAPI_PATHS.crawlerStrategies),
    requestJson<{ accounts: ConsoleSnapshot["crawlerAccounts"] }>(OPENAPI_PATHS.crawlerAccounts),
    requestJson<{ platforms: ConsoleSnapshot["platforms"] }>(OPENAPI_PATHS.platforms),
    requestJson<{ fields: ConfigField[] }>(OPENAPI_PATHS.systemConfig),
    requestJson<{ lines: ConsoleSnapshot["logs"] }>(`${OPENAPI_PATHS.logs}?tail=300`)
  ]);
  const identityRulePages = await Promise.all(
    platformPage.platforms.map((platform) =>
      requestJson<{ rules: IdentityRule[] }>(OPENAPI_PATHS.platformIdentityRules(platform.id))
    )
  );

  return {
    workspaceId,
    generatedAt: taskTimestamp(),
    mock: false,
    components: components.components,
    reportTemplates: templates.templates,
    reportTasks: reportTaskPage.tasks,
    crawlerTasks: crawlerTaskPage.tasks,
    crawlerStrategies: strategies.strategies,
    crawlerAccounts: accountPage.accounts,
    platforms: platformPage.platforms,
    identityRules: identityRulePages.flatMap((page) => page.rules),
    configFields: config.fields,
    logs: logPage.lines
  };
}

export async function createReportTask(input: CreateReportTaskInput): Promise<ReportTask> {
  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ task: ReportTask }>(OPENAPI_PATHS.reportTasks, {
      method: "POST",
      body: JSON.stringify(input)
    });
    return response.task;
  }

  const timestamp = taskTimestamp();
  const task: ReportTask = {
    id: nextId("report"),
    workspaceId,
    topic: input.topic,
    status: "queued",
    progress: 0,
    stage: "queued",
    templateId: input.templateId,
    artifacts: input.outputFormats.map((format) => ({
      format,
      ready: false
    })),
    owner: input.owner,
    createdAt: timestamp,
    updatedAt: timestamp
  };
  reportTasks.unshift(task);
  addLog("report", `Report task ${task.id} queued`, task.id);
  return task;
}

export async function cancelReportTask(taskId: string): Promise<ReportTask> {
  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ task: ReportTask }>(OPENAPI_PATHS.reportTaskCancel(taskId), {
      method: "POST"
    });
    return response.task;
  }

  const task = reportTasks.find((item) => item.id === taskId);
  if (!task) throw new Error("Task not found");
  task.status = "cancelled";
  task.progress = Math.max(task.progress, 0);
  task.updatedAt = taskTimestamp();
  addLog("report", `Report task ${task.id} cancelled`, task.id);
  return task;
}

export async function createCrawlerTask(input: CreateCrawlerTaskInput): Promise<CrawlerTask> {
  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ task: CrawlerTask }>(OPENAPI_PATHS.crawlerTasks, {
      method: "POST",
      body: JSON.stringify(input)
    });
    return response.task;
  }

  const timestamp = taskTimestamp();
  const task: CrawlerTask = {
    id: nextId("crawler"),
    workspaceId,
    runMode: input.runMode,
    status: "queued",
    progress: 0,
    strategyId: input.strategyId,
    targetDate: input.targetDate,
    platforms: input.platforms,
    keywords: input.keywords,
    keywordSource: input.keywordSource,
    stats: {
      totalKeywords: input.keywords.length,
      totalPlatforms: input.platforms.length,
      totalTasks: input.keywords.length * input.platforms.length,
      successfulTasks: 0,
      failedTasks: 0,
      totalNotes: 0,
      totalComments: 0
    },
    owner: input.owner,
    createdAt: timestamp,
    updatedAt: timestamp
  };
  crawlerTasks.unshift(task);
  addLog("crawler", `Crawler task ${task.id} queued`, task.id);
  return task;
}

export async function stopCrawlerTask(taskId: string): Promise<CrawlerTask> {
  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ task: CrawlerTask }>(OPENAPI_PATHS.crawlerTaskStop(taskId), {
      method: "POST"
    });
    return response.task;
  }

  const task = crawlerTasks.find((item) => item.id === taskId);
  if (!task) throw new Error("Task not found");
  task.status = "stopping";
  task.updatedAt = taskTimestamp();
  addLog("crawler", `Crawler task ${task.id} stopping`, task.id);
  return task;
}

export async function updatePlatformPolicy(
  platformId: PlatformId,
  policy: PlatformPolicy
): Promise<PlatformPolicy> {
  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ policy: PlatformPolicy }>(OPENAPI_PATHS.platformPolicy(platformId), {
      method: "PUT",
      body: JSON.stringify(policy)
    });
    return response.policy;
  }

  const platform = platforms.find((item) => item.id === platformId);
  if (!platform) throw new Error("Platform not found");
  const updated = {
    ...policy,
    platformId,
    updatedAt: taskTimestamp()
  };
  platform.policy = updated;
  platform.enabled = updated.enabled;
  addLog("system", `Platform policy updated for ${platformId}`);
  return updated;
}

export async function createIdentityRule(input: IdentityRuleInput): Promise<IdentityRule> {
  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ rule: IdentityRule }>(
      OPENAPI_PATHS.platformIdentityRules(input.platformId),
      {
        method: "POST",
        body: JSON.stringify(input)
      }
    );
    return response.rule;
  }

  const rule: IdentityRule = {
    id: nextId("rule"),
    platformId: input.platformId,
    listType: input.listType,
    userId: input.userId,
    label: input.label,
    reason: input.reason,
    createdAt: taskTimestamp(),
    createdBy: input.createdBy
  };
  identityRules.unshift(rule);
  const platform = platforms.find((item) => item.id === input.platformId);
  if (platform) {
    platform.identityRuleCounts[input.listType] += 1;
  }
  addLog("system", `${input.listType} rule added for ${input.platformId}`);
  return rule;
}

export async function deleteIdentityRule(platformId: PlatformId, ruleId: string): Promise<void> {
  if (!USE_MOCKS && API_BASE_URL) {
    await requestJson<void>(OPENAPI_PATHS.platformIdentityRule(platformId, ruleId), {
      method: "DELETE"
    });
    return;
  }

  const index = identityRules.findIndex((item) => item.id === ruleId);
  if (index >= 0) {
    const [removed] = identityRules.splice(index, 1);
    const platform = platforms.find((item) => item.id === platformId);
    if (platform) {
      platform.identityRuleCounts[removed.listType] = Math.max(
        0,
        platform.identityRuleCounts[removed.listType] - 1
      );
    }
  }
  addLog("system", `Identity rule ${ruleId} deleted`);
}

export async function updateSystemConfig(values: Record<string, string>): Promise<ConfigField[]> {
  const cleanedEntries = Object.entries(values).filter(([, value]) => value !== "");

  if (!USE_MOCKS && API_BASE_URL) {
    const response = await requestJson<{ fields: ConfigField[] }>(OPENAPI_PATHS.systemConfig, {
      method: "PATCH",
      body: JSON.stringify({
        values: Object.fromEntries(cleanedEntries)
      })
    });
    return response.fields;
  }

  for (const [key, value] of cleanedEntries) {
    const field = configFields.find((item) => item.key === key);
    if (field && !field.sensitive) {
      field.value = value;
    }
  }
  addLog("system", "System config updated");
  return configFields.map((field) => ({ ...field }));
}
