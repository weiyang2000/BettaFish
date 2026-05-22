export type TaskStatus =
  | "queued"
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "stopping"
  | "stopped";

export type ComponentStatus =
  | "unknown"
  | "stopped"
  | "starting"
  | "running"
  | "degraded"
  | "failed"
  | "stopping";

export type ComponentId =
  | "query"
  | "media"
  | "insight"
  | "forum"
  | "report"
  | "mindspider"
  | "database";

export type PlatformId = "xhs" | "dy" | "ks" | "bili" | "wb" | "tieba" | "zhihu";

export type ReportFormat = "html" | "json" | "md" | "pdf";

export type RunMode = "topic_extraction" | "deep_sentiment" | "full_workflow";

export type IdentityListType = "allow" | "block";

export type LogLevel = "debug" | "info" | "warning" | "error" | "critical";

export type LogSource =
  | "system"
  | "query"
  | "media"
  | "insight"
  | "forum"
  | "report"
  | "mindspider"
  | "crawler";

export interface UserRef {
  userId: string;
  displayName: string;
  role?: "owner" | "operator" | "reviewer" | "service_account";
}

export interface SystemComponent {
  id: ComponentId;
  name: string;
  status: ComponentStatus;
  port?: number;
  outputLines?: number;
  lastHeartbeatAt?: string;
  message?: string;
}

export interface ReportArtifact {
  format: ReportFormat;
  ready: boolean;
  filename?: string;
  sizeBytes?: number;
  downloadUrl?: string;
}

export interface ReportTask {
  id: string;
  workspaceId: string;
  topic: string;
  status: Exclude<TaskStatus, "stopping" | "stopped">;
  progress: number;
  stage:
    | "queued"
    | "prepare"
    | "io_ready"
    | "data_loaded"
    | "agent_running"
    | "retry_wait"
    | "persist"
    | "completed"
    | "failed";
  templateId?: string;
  artifacts: ReportArtifact[];
  owner?: UserRef;
  createdAt: string;
  updatedAt: string;
  errorMessage?: string;
}

export interface CrawlerStats {
  totalKeywords: number;
  totalPlatforms: number;
  totalTasks: number;
  successfulTasks: number;
  failedTasks: number;
  totalNotes: number;
  totalComments: number;
}

export interface CrawlerTask {
  id: string;
  workspaceId: string;
  runMode: RunMode;
  status: TaskStatus;
  progress: number;
  strategyId?: string;
  targetDate?: string;
  platforms: PlatformId[];
  stats: CrawlerStats;
  owner?: UserRef;
  createdAt: string;
  updatedAt: string;
  errorMessage?: string;
}

export interface CrawlFrequency {
  mode: "manual" | "hourly" | "daily" | "weekly" | "cron";
  cron?: string;
  timezone: string;
}

export interface PlatformPolicy {
  platformId: PlatformId;
  enabled: boolean;
  crawlDepth: number;
  maxKeywords: number;
  maxNotesPerKeyword: number;
  maxCommentsPerNote: number;
  keywords: string[];
  keywordSource: "manual" | "broad_topic_extraction" | "mixed";
  frequency: CrawlFrequency;
  loginType: "qrcode" | "phone" | "cookie";
  headless: boolean;
  updatedAt: string;
}

export interface Platform {
  id: PlatformId;
  name: string;
  enabled: boolean;
  crawlerType: "search" | "detail" | "creator";
  policy: PlatformPolicy;
  identityRuleCounts: {
    allow: number;
    block: number;
  };
}

export interface IdentityRule {
  id: string;
  platformId: PlatformId;
  listType: IdentityListType;
  userId: string;
  label?: string;
  reason?: string;
  expiresAt?: string;
  createdAt: string;
  createdBy?: UserRef;
}

export interface ConfigField {
  key: string;
  label: string;
  group: "server" | "database" | "llm" | "search" | "crawler";
  type: "string" | "number" | "boolean" | "enum" | "secret" | "url";
  value: string;
  editable: boolean;
  sensitive: boolean;
  required?: boolean;
  options?: string[];
}

export interface LogLine {
  id: string;
  source: LogSource;
  level: LogLevel;
  timestamp: string;
  message: string;
  taskId?: string;
}

export interface ReportTemplate {
  id: string;
  name: string;
  filename: string;
  description: string;
  sizeBytes: number;
}

export interface CrawlerStrategy {
  id: string;
  workspaceId: string;
  name: string;
  runMode: RunMode;
  platformPolicies: PlatformPolicy[];
  createdAt: string;
  updatedAt: string;
}

export interface ConsoleSnapshot {
  workspaceId: string;
  generatedAt: string;
  mock: boolean;
  components: SystemComponent[];
  reportTasks: ReportTask[];
  reportTemplates: ReportTemplate[];
  crawlerTasks: CrawlerTask[];
  crawlerStrategies: CrawlerStrategy[];
  platforms: Platform[];
  identityRules: IdentityRule[];
  configFields: ConfigField[];
  logs: LogLine[];
}

export interface CreateReportTaskInput {
  topic: string;
  templateId?: string;
  outputFormats: ReportFormat[];
  owner: UserRef;
}

export interface CreateCrawlerTaskInput {
  strategyId?: string;
  runMode: RunMode;
  targetDate: string;
  platforms: PlatformId[];
  owner: UserRef;
}

export interface IdentityRuleInput {
  platformId: PlatformId;
  listType: IdentityListType;
  userId: string;
  label?: string;
  reason?: string;
  createdBy: UserRef;
}
