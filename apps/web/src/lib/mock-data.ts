import type {
  ComponentStatus,
  ConfigField,
  ConsoleSnapshot,
  CrawlerStrategy,
  CrawlerTask,
  IdentityRule,
  LogLine,
  Platform,
  PlatformId,
  PlatformPolicy,
  ReportTask,
  ReportTemplate,
  SystemComponent
} from "./types";

export const WORKSPACE_ID = "workspace_demo";

const now = "2026-05-22T09:45:00Z";

const policy = (
  platformId: PlatformId,
  overrides: Partial<PlatformPolicy> = {}
): PlatformPolicy => ({
  platformId,
  enabled: true,
  crawlDepth: 3,
  maxKeywords: 80,
  maxNotesPerKeyword: 40,
  maxCommentsPerNote: 120,
  keywords: ["养老服务", "社区护理", "银发经济"],
  keywordSource: "mixed",
  frequency: {
    mode: "daily",
    timezone: "Asia/Shanghai"
  },
  loginType: "qrcode",
  headless: true,
  updatedAt: now,
  ...overrides
});

export const components: SystemComponent[] = [
  {
    id: "database",
    name: "Database",
    status: "running",
    port: 5432,
    outputLines: 128,
    lastHeartbeatAt: now,
    message: "PostgreSQL connection ready"
  },
  {
    id: "query",
    name: "Query Engine",
    status: "running",
    port: 8503,
    outputLines: 248,
    lastHeartbeatAt: now,
    message: "Search API ready"
  },
  {
    id: "media",
    name: "Media Engine",
    status: "running",
    port: 8502,
    outputLines: 311,
    lastHeartbeatAt: now,
    message: "Media summaries available"
  },
  {
    id: "insight",
    name: "Insight Engine",
    status: "degraded",
    port: 8501,
    outputLines: 402,
    lastHeartbeatAt: now,
    message: "High latency from LLM provider"
  },
  {
    id: "forum",
    name: "Forum Engine",
    status: "running",
    outputLines: 96,
    lastHeartbeatAt: now,
    message: "Agent forum monitor active"
  },
  {
    id: "report",
    name: "Report Engine",
    status: "running",
    outputLines: 188,
    lastHeartbeatAt: now,
    message: "SSE bridge initialized"
  },
  {
    id: "mindspider",
    name: "MindSpider",
    status: "stopped",
    outputLines: 17,
    message: "No crawler task is running"
  }
];

export const reportTemplates: ReportTemplate[] = [
  {
    id: "daily-monitoring",
    name: "日常舆情监测",
    filename: "日常或定期舆情监测报告模板.md",
    description: "适合周期性输出热点趋势、传播路径、情绪与风险研判。",
    sizeBytes: 8304
  },
  {
    id: "crisis-response",
    name: "突发事件危机公关",
    filename: "突发事件与危机公关舆情报告模板.md",
    description: "适合突发事件复盘、态势追踪与处置建议。",
    sizeBytes: 9088
  },
  {
    id: "industry-policy",
    name: "政策行业动态",
    filename: "特定政策或行业动态舆情分析报告模板.md",
    description: "适合政策传播、行业趋势和利益相关方分析。",
    sizeBytes: 7596
  }
];

export const reportTasks: ReportTask[] = [
  {
    id: "report_20260522_001",
    workspaceId: WORKSPACE_ID,
    topic: "养老服务发展趋势",
    status: "succeeded",
    progress: 100,
    stage: "completed",
    templateId: "daily-monitoring",
    artifacts: [
      {
        format: "html",
        ready: true,
        filename: "report_养老服务发展趋势.html",
        sizeBytes: 214_820,
        downloadUrl: "/api/v1/report-tasks/report_20260522_001/exports/html"
      },
      {
        format: "pdf",
        ready: true,
        filename: "report_养老服务发展趋势.pdf",
        sizeBytes: 1_024_210,
        downloadUrl: "/api/v1/report-tasks/report_20260522_001/exports/pdf"
      },
      {
        format: "md",
        ready: true,
        filename: "report_养老服务发展趋势.md",
        sizeBytes: 88_210,
        downloadUrl: "/api/v1/report-tasks/report_20260522_001/exports/md"
      }
    ],
    owner: {
      userId: "user_demo",
      displayName: "Demo Operator",
      role: "operator"
    },
    createdAt: "2026-05-22T08:20:00Z",
    updatedAt: "2026-05-22T08:36:40Z"
  },
  {
    id: "report_20260522_002",
    workspaceId: WORKSPACE_ID,
    topic: "AI 教育硬件口碑变化",
    status: "running",
    progress: 58,
    stage: "agent_running",
    templateId: "industry-policy",
    artifacts: [
      {
        format: "html",
        ready: false
      },
      {
        format: "pdf",
        ready: false
      }
    ],
    owner: {
      userId: "user_demo",
      displayName: "Demo Operator",
      role: "operator"
    },
    createdAt: "2026-05-22T09:18:00Z",
    updatedAt: "2026-05-22T09:42:31Z"
  }
];

export const crawlerTasks: CrawlerTask[] = [
  {
    id: "crawler_20260522_001",
    workspaceId: WORKSPACE_ID,
    runMode: "full_workflow",
    status: "succeeded",
    progress: 100,
    strategyId: "strategy_daily_hot_topics",
    targetDate: "2026-05-22",
    platforms: ["wb", "xhs", "zhihu"],
    stats: {
      totalKeywords: 72,
      totalPlatforms: 3,
      totalTasks: 216,
      successfulTasks: 212,
      failedTasks: 4,
      totalNotes: 8420,
      totalComments: 34182
    },
    owner: {
      userId: "user_demo",
      displayName: "Demo Operator"
    },
    createdAt: "2026-05-22T06:00:00Z",
    updatedAt: "2026-05-22T06:48:00Z"
  },
  {
    id: "crawler_20260522_002",
    workspaceId: WORKSPACE_ID,
    runMode: "deep_sentiment",
    status: "running",
    progress: 44,
    strategyId: "strategy_brand_watch",
    targetDate: "2026-05-22",
    platforms: ["dy", "bili"],
    stats: {
      totalKeywords: 24,
      totalPlatforms: 2,
      totalTasks: 48,
      successfulTasks: 19,
      failedTasks: 0,
      totalNotes: 1292,
      totalComments: 5876
    },
    owner: {
      userId: "user_demo",
      displayName: "Demo Operator"
    },
    createdAt: "2026-05-22T09:05:00Z",
    updatedAt: "2026-05-22T09:44:00Z"
  }
];

export const platforms: Platform[] = [
  {
    id: "wb",
    name: "微博",
    enabled: true,
    crawlerType: "search",
    policy: policy("wb", {
      crawlDepth: 4,
      maxCommentsPerNote: 200,
      keywords: ["养老服务", "医保支付", "养老院"]
    }),
    identityRuleCounts: {
      allow: 1,
      block: 2
    }
  },
  {
    id: "xhs",
    name: "小红书",
    enabled: true,
    crawlerType: "search",
    policy: policy("xhs", {
      maxNotesPerKeyword: 60,
      keywords: ["社区护理", "适老化改造", "康养"]
    }),
    identityRuleCounts: {
      allow: 0,
      block: 1
    }
  },
  {
    id: "zhihu",
    name: "知乎",
    enabled: true,
    crawlerType: "search",
    policy: policy("zhihu", {
      crawlDepth: 2,
      maxKeywords: 40,
      keywords: ["老龄化", "养老政策"]
    }),
    identityRuleCounts: {
      allow: 0,
      block: 0
    }
  },
  {
    id: "dy",
    name: "抖音",
    enabled: true,
    crawlerType: "search",
    policy: policy("dy", {
      loginType: "cookie",
      maxNotesPerKeyword: 35,
      maxCommentsPerNote: 80
    }),
    identityRuleCounts: {
      allow: 2,
      block: 0
    }
  },
  {
    id: "bili",
    name: "Bilibili",
    enabled: true,
    crawlerType: "search",
    policy: policy("bili", {
      frequency: {
        mode: "weekly",
        timezone: "Asia/Shanghai"
      }
    }),
    identityRuleCounts: {
      allow: 0,
      block: 0
    }
  },
  {
    id: "tieba",
    name: "贴吧",
    enabled: false,
    crawlerType: "search",
    policy: policy("tieba", {
      enabled: false,
      frequency: {
        mode: "manual",
        timezone: "Asia/Shanghai"
      }
    }),
    identityRuleCounts: {
      allow: 0,
      block: 0
    }
  },
  {
    id: "ks",
    name: "快手",
    enabled: false,
    crawlerType: "search",
    policy: policy("ks", {
      enabled: false,
      headless: false
    }),
    identityRuleCounts: {
      allow: 0,
      block: 0
    }
  }
];

export const identityRules: IdentityRule[] = [
  {
    id: "rule_001",
    platformId: "wb",
    listType: "block",
    userId: "spam_7788",
    label: "重复营销号",
    reason: "高频广告内容影响情绪统计",
    createdAt: "2026-05-20T11:10:00Z"
  },
  {
    id: "rule_002",
    platformId: "wb",
    listType: "allow",
    userId: "gov_service_account",
    label: "政务发布",
    reason: "权威口径优先保留",
    createdAt: "2026-05-21T08:00:00Z"
  },
  {
    id: "rule_003",
    platformId: "xhs",
    listType: "block",
    userId: "seller_3910",
    label: "导流商家",
    reason: "导购内容不进入报告素材",
    createdAt: "2026-05-21T13:42:00Z"
  }
];

export const configFields: ConfigField[] = [
  {
    key: "HOST",
    label: "服务主机",
    group: "server",
    type: "string",
    value: "0.0.0.0",
    editable: true,
    sensitive: false
  },
  {
    key: "PORT",
    label: "服务端口",
    group: "server",
    type: "number",
    value: "5000",
    editable: true,
    sensitive: false
  },
  {
    key: "DB_DIALECT",
    label: "数据库类型",
    group: "database",
    type: "enum",
    value: "postgresql",
    options: ["postgresql", "mysql"],
    editable: true,
    sensitive: false
  },
  {
    key: "DB_HOST",
    label: "数据库主机",
    group: "database",
    type: "string",
    value: "db.internal",
    editable: true,
    sensitive: false
  },
  {
    key: "DB_PASSWORD",
    label: "数据库密码",
    group: "database",
    type: "secret",
    value: "********",
    editable: true,
    sensitive: true
  },
  {
    key: "REPORT_ENGINE_MODEL_NAME",
    label: "Report 模型",
    group: "llm",
    type: "string",
    value: "gemini-2.5-pro",
    editable: true,
    sensitive: false
  },
  {
    key: "REPORT_ENGINE_API_KEY",
    label: "Report API Key",
    group: "llm",
    type: "secret",
    value: "********",
    editable: true,
    sensitive: true
  },
  {
    key: "MINDSPIDER_MODEL_NAME",
    label: "MindSpider 模型",
    group: "crawler",
    type: "string",
    value: "deepseek-chat",
    editable: true,
    sensitive: false
  },
  {
    key: "MINDSPIDER_API_KEY",
    label: "MindSpider API Key",
    group: "crawler",
    type: "secret",
    value: "********",
    editable: true,
    sensitive: true
  },
  {
    key: "SEARCH_TOOL_TYPE",
    label: "搜索工具",
    group: "search",
    type: "enum",
    value: "AnspireAPI",
    options: ["AnspireAPI", "BochaAPI"],
    editable: true,
    sensitive: false
  },
  {
    key: "ANSPIRE_API_KEY",
    label: "Anspire API Key",
    group: "search",
    type: "secret",
    value: "********",
    editable: true,
    sensitive: true
  }
];

export const logs: LogLine[] = [
  {
    id: "log_001",
    source: "system",
    level: "info",
    timestamp: "2026-05-22T09:41:04Z",
    message: "Component status snapshot completed"
  },
  {
    id: "log_002",
    source: "report",
    level: "info",
    timestamp: "2026-05-22T09:41:22Z",
    message: "Report task report_20260522_002 entered agent_running stage",
    taskId: "report_20260522_002"
  },
  {
    id: "log_003",
    source: "insight",
    level: "warning",
    timestamp: "2026-05-22T09:42:10Z",
    message: "LLM latency exceeded 15 seconds; retry budget remains 2"
  },
  {
    id: "log_004",
    source: "crawler",
    level: "info",
    timestamp: "2026-05-22T09:43:03Z",
    message: "dy platform crawler saved 312 notes and 1480 comments",
    taskId: "crawler_20260522_002"
  },
  {
    id: "log_005",
    source: "forum",
    level: "info",
    timestamp: "2026-05-22T09:44:31Z",
    message: "Forum host collected Query, Media, and Insight responses"
  }
];

export const crawlerStrategies: CrawlerStrategy[] = [
  {
    id: "strategy_daily_hot_topics",
    workspaceId: WORKSPACE_ID,
    name: "每日热点全流程",
    runMode: "full_workflow",
    platformPolicies: [platforms[0].policy, platforms[1].policy, platforms[2].policy],
    createdAt: "2026-05-18T02:00:00Z",
    updatedAt: "2026-05-22T06:00:00Z"
  },
  {
    id: "strategy_brand_watch",
    workspaceId: WORKSPACE_ID,
    name: "品牌声量监测",
    runMode: "deep_sentiment",
    platformPolicies: [platforms[3].policy, platforms[4].policy],
    createdAt: "2026-05-19T08:00:00Z",
    updatedAt: "2026-05-22T09:00:00Z"
  }
];

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function getMockSnapshot(): ConsoleSnapshot {
  return clone({
    workspaceId: WORKSPACE_ID,
    generatedAt: now,
    mock: true,
    components,
    reportTasks,
    reportTemplates,
    crawlerTasks,
    crawlerStrategies,
    platforms,
    identityRules,
    configFields,
    logs
  });
}

export function componentTone(status: ComponentStatus): "good" | "warn" | "bad" | "idle" {
  if (status === "running") return "good";
  if (status === "degraded" || status === "starting" || status === "stopping") return "warn";
  if (status === "failed") return "bad";
  return "idle";
}
