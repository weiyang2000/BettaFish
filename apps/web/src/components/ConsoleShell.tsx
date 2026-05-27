"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  CheckCircle2,
  CircleStop,
  ClipboardList,
  Database,
  Download,
  FilePlus2,
  Filter,
  Gauge,
  LayoutDashboard,
  ListChecks,
  Loader2,
  LockKeyhole,
  Play,
  RefreshCcw,
  Save,
  Settings,
  Shield,
  SlidersHorizontal,
  Square,
  StopCircle,
  TerminalSquare,
  Trash2,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  cancelReportTask,
  createCrawlerTask,
  createIdentityRule,
  createReportTask,
  deleteIdentityRule,
  loadConsoleSnapshot,
  stopCrawlerTask,
  updatePlatformPolicy,
  updateSystemConfig
} from "@/lib/openapi-client";
import type {
  ComponentStatus,
  ConfigField,
  ConsoleSnapshot,
  CrawlerAccountStatus,
  CrawlerTaskKeywordSource,
  CrawlerTask,
  IdentityRule,
  Platform,
  PlatformId,
  PlatformPolicy,
  ReportFormat,
  ReportTask,
  RunMode,
  TaskStatus
} from "@/lib/types";

type Section = "dashboard" | "reports" | "crawlers" | "platforms" | "config" | "logs";

const currentUser = {
  userId: "user_demo",
  displayName: "Demo Operator",
  role: "operator" as const
};

const navItems: Array<{ id: Section; label: string; icon: React.ComponentType<{ size?: number }> }> = [
  { id: "dashboard", label: "总览", icon: LayoutDashboard },
  { id: "reports", label: "报告", icon: ClipboardList },
  { id: "crawlers", label: "爬虫", icon: Bot },
  { id: "platforms", label: "平台规则", icon: Shield },
  { id: "config", label: "系统配置", icon: Settings },
  { id: "logs", label: "运行日志", icon: TerminalSquare }
];

const platformNames: Record<PlatformId, string> = {
  wb: "微博",
  xhs: "小红书",
  zhihu: "知乎",
  dy: "抖音",
  bili: "Bilibili",
  tieba: "贴吧",
  ks: "快手"
};

const loginTypeLabels: Record<PlatformPolicy["loginType"], string> = {
  qrcode: "扫码",
  phone: "手机号",
  cookie: "Cookie"
};

function classNames(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(" ");
}

function statusTone(status: TaskStatus | ComponentStatus | CrawlerAccountStatus) {
  if (status === "running" || status === "succeeded" || status === "active") return "good";
  if (
    status === "queued" ||
    status === "pending" ||
    status === "starting" ||
    status === "degraded" ||
    status === "login_required" ||
    status === "unknown"
  ) {
    return "warn";
  }
  if (status === "failed" || status === "expired" || status === "disabled" || status === "error") return "bad";
  return "idle";
}

function StatusBadge({ value }: { value: TaskStatus | ComponentStatus | CrawlerAccountStatus }) {
  return <span className={classNames("status-badge", `tone-${statusTone(value)}`)}>{value}</span>;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress-track" aria-label={`progress ${value}%`}>
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

function SectionHeader({
  title,
  subtitle,
  action
}: {
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state">
      <ListChecks size={28} />
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function MetricTile({
  label,
  value,
  detail,
  icon: Icon
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ComponentType<{ size?: number }>;
}) {
  return (
    <div className="metric-tile">
      <div className="metric-icon">
        <Icon size={20} />
      </div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function replaceReportTask(tasks: ReportTask[], updated: ReportTask) {
  return tasks.map((task) => (task.id === updated.id ? updated : task));
}

function replaceCrawlerTask(tasks: CrawlerTask[], updated: CrawlerTask) {
  return tasks.map((task) => (task.id === updated.id ? updated : task));
}

export function ConsoleShell() {
  const [activeSection, setActiveSection] = useState<Section>("dashboard");
  const [snapshot, setSnapshot] = useState<ConsoleSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedPlatformId, setSelectedPlatformId] = useState<PlatformId>("wb");
  const [accountPlatformFilter, setAccountPlatformFilter] = useState<PlatformId | "all">("all");
  const [accountStatusFilter, setAccountStatusFilter] = useState<CrawlerAccountStatus | "all">("all");
  const [policyDraft, setPolicyDraft] = useState<PlatformPolicy | null>(null);
  const [logSource, setLogSource] = useState<string>("all");
  const [configDraft, setConfigDraft] = useState<Record<string, string>>({});
  const [reportForm, setReportForm] = useState({
    topic: "",
    templateId: "daily-monitoring",
    formats: {
      html: true,
      md: false,
      pdf: true,
      json: false
    } satisfies Record<ReportFormat, boolean>
  });
  const [crawlerForm, setCrawlerForm] = useState<{
    runMode: RunMode;
    targetDate: string;
    platforms: PlatformId[];
    keywords: string;
    keywordSource: CrawlerTaskKeywordSource;
    maxNotesPerKeyword: number;
    maxCommentsPerNote: number;
    loginType: PlatformPolicy["loginType"];
    headless: boolean;
  }>({
    runMode: "deep_sentiment",
    targetDate: "2026-05-22",
    platforms: ["wb"] as PlatformId[],
    keywords: "养老服务\n医保支付",
    keywordSource: "manual",
    maxNotesPerKeyword: 50,
    maxCommentsPerNote: 100,
    loginType: "qrcode",
    headless: true
  });
  const [identityForm, setIdentityForm] = useState({
    userId: "",
    label: "",
    reason: ""
  });

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await loadConsoleSnapshot();
      setSnapshot(data);
      const firstPlatform = data.platforms[0]?.id ?? "wb";
      setSelectedPlatformId(firstPlatform);
      setPolicyDraft(data.platforms.find((item) => item.id === firstPlatform)?.policy ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    setPolicyDraft(snapshot.platforms.find((item) => item.id === selectedPlatformId)?.policy ?? null);
  }, [selectedPlatformId, snapshot]);

  const metrics = useMemo(() => {
    if (!snapshot) return null;
    const runningComponents = snapshot.components.filter((item) => item.status === "running").length;
    const runningReports = snapshot.reportTasks.filter((task) => task.status === "running").length;
    const crawlerNotes = snapshot.crawlerTasks.reduce((sum, task) => sum + task.stats.totalNotes, 0);
    const blockedUsers = snapshot.identityRules.filter((rule) => rule.listType === "block").length;
    return { runningComponents, runningReports, crawlerNotes, blockedUsers };
  }, [snapshot]);

  const selectedPlatform = snapshot?.platforms.find((item) => item.id === selectedPlatformId) ?? null;
  const selectedRules =
    snapshot?.identityRules.filter((rule) => rule.platformId === selectedPlatformId && rule.listType === "block") ?? [];
  const selectedLegacyAllowRuleCount =
    snapshot?.identityRules.filter((rule) => rule.platformId === selectedPlatformId && rule.listType === "allow").length ??
    0;
  const filteredCrawlerAccounts =
    snapshot?.crawlerAccounts.filter((account) => {
      const platformMatches = accountPlatformFilter === "all" || account.platformId === accountPlatformFilter;
      const statusMatches = accountStatusFilter === "all" || account.status === accountStatusFilter;
      return platformMatches && statusMatches;
    }) ?? [];
  const filteredLogs =
    snapshot?.logs.filter((line) => logSource === "all" || line.source === logSource) ?? [];

  async function runAction(label: string, action: () => Promise<void>) {
    setBusyAction(label);
    setNotice(null);
    try {
      await action();
      setNotice(label);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusyAction(null);
    }
  }

  const createReport = () =>
    runAction("报告任务已创建", async () => {
      if (!snapshot) return;
      const topic = reportForm.topic.trim();
      if (!topic) throw new Error("报告主题不能为空");
      const outputFormats = Object.entries(reportForm.formats)
        .filter(([, enabled]) => enabled)
        .map(([format]) => format as ReportFormat);
      if (outputFormats.length === 0) throw new Error("至少选择一种导出格式");

      const task = await createReportTask({
        topic,
        templateId: reportForm.templateId,
        outputFormats,
        owner: currentUser
      });
      setSnapshot({
        ...snapshot,
        reportTasks: [task, ...snapshot.reportTasks]
      });
      setReportForm((current) => ({ ...current, topic: "" }));
    });

  const createCrawler = () =>
    runAction("爬虫任务已创建", async () => {
      if (!snapshot) return;
      if (crawlerForm.platforms.length === 0) throw new Error("至少选择一个平台");
      const keywords = Array.from(
        new Set(
          crawlerForm.keywords
            .split(/\r?\n|,/)
            .map((item) => item.trim())
            .filter(Boolean)
        )
      );
      if (keywords.length === 0) throw new Error("至少输入一个关键词");
      const task = await createCrawlerTask({
        runMode: crawlerForm.runMode,
        targetDate: crawlerForm.targetDate,
        platforms: crawlerForm.platforms,
        keywords,
        keywordSource: crawlerForm.keywordSource,
        maxNotesPerKeyword: crawlerForm.maxNotesPerKeyword,
        maxCommentsPerNote: crawlerForm.maxCommentsPerNote,
        loginType: crawlerForm.loginType,
        headless: crawlerForm.headless,
        owner: currentUser
      });
      setSnapshot({
        ...snapshot,
        crawlerTasks: [task, ...snapshot.crawlerTasks]
      });
    });

  const savePolicy = () =>
    runAction("平台策略已保存", async () => {
      if (!snapshot || !policyDraft) return;
      const policy = await updatePlatformPolicy(selectedPlatformId, policyDraft);
      setSnapshot({
        ...snapshot,
        platforms: snapshot.platforms.map((platform) =>
          platform.id === selectedPlatformId
            ? {
                ...platform,
                enabled: policy.enabled,
                policy
              }
            : platform
        )
      });
    });

  const addIdentity = () =>
    runAction("黑名单规则已添加", async () => {
      if (!snapshot) return;
      const userId = identityForm.userId.trim();
      if (!userId) throw new Error("用户 ID 不能为空");
      const rule = await createIdentityRule({
        platformId: selectedPlatformId,
        listType: "block",
        userId,
        label: identityForm.label.trim(),
        reason: identityForm.reason.trim(),
        createdBy: currentUser
      });
      setSnapshot({
        ...snapshot,
        identityRules: [rule, ...snapshot.identityRules],
        platforms: snapshot.platforms.map((platform) =>
          platform.id === selectedPlatformId
            ? {
                ...platform,
                identityRuleCounts: {
                  ...platform.identityRuleCounts,
                  [rule.listType]: platform.identityRuleCounts[rule.listType] + 1
                }
              }
            : platform
        )
      });
      setIdentityForm((current) => ({ ...current, userId: "", label: "", reason: "" }));
    });

  const removeIdentity = (rule: IdentityRule) =>
    runAction("黑名单规则已删除", async () => {
      if (!snapshot) return;
      await deleteIdentityRule(rule.platformId, rule.id);
      setSnapshot({
        ...snapshot,
        identityRules: snapshot.identityRules.filter((item) => item.id !== rule.id),
        platforms: snapshot.platforms.map((platform) =>
          platform.id === rule.platformId
            ? {
                ...platform,
                identityRuleCounts: {
                  ...platform.identityRuleCounts,
                  [rule.listType]: Math.max(0, platform.identityRuleCounts[rule.listType] - 1)
                }
              }
            : platform
        )
      });
    });

  const saveConfig = () =>
    runAction("系统配置已保存", async () => {
      if (!snapshot) return;
      const fields = await updateSystemConfig(configDraft);
      setSnapshot({
        ...snapshot,
        configFields: fields
      });
      setConfigDraft({});
    });

  const setPolicyValue = <K extends keyof PlatformPolicy>(key: K, value: PlatformPolicy[K]) => {
    setPolicyDraft((current) => (current ? { ...current, [key]: value } : current));
  };

  if (loading) {
    return (
      <main className="loading-screen">
        <Loader2 className="spin" size={32} />
        <span>正在加载 SaaS 控制台</span>
      </main>
    );
  }

  if (error && !snapshot) {
    return (
      <main className="error-screen">
        <AlertTriangle size={34} />
        <strong>控制台加载失败</strong>
        <span>{error}</span>
        <button className="primary-button" onClick={() => void load()}>
          <RefreshCcw size={16} />
          重试
        </button>
      </main>
    );
  }

  if (!snapshot || !metrics) {
    return null;
  }

  return (
    <div className="console-root">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">BF</div>
          <div>
            <strong>BettaFish</strong>
            <span>SaaS Console</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="Console sections">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={classNames("nav-button", activeSection === item.id && "active")}
                onClick={() => setActiveSection(item.id)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="workspace-panel">
          <span>Workspace</span>
          <strong>{snapshot.workspaceId}</strong>
          <small>{snapshot.mock ? "Mock adapter" : "API connected"}</small>
        </div>
      </aside>

      <main className="main-surface">
        <header className="topbar">
          <div>
            <h1>舆情 SaaS 控制台</h1>
            <p>报告、爬虫、平台策略与运行状态统一入口</p>
          </div>
          <div className="topbar-actions">
            {notice && <span className="notice">{notice}</span>}
            {error && (
              <button className="ghost-button error-inline" onClick={() => setError(null)}>
                <XCircle size={16} />
                {error}
              </button>
            )}
            <button className="icon-button" title="刷新" onClick={() => void load()}>
              <RefreshCcw size={18} />
            </button>
          </div>
        </header>

        {activeSection === "dashboard" && (
          <section className="section-band">
            <SectionHeader title="运行总览" subtitle="引擎、任务与策略的实时摘要" />
            <div className="metric-grid">
              <MetricTile
                label="运行组件"
                value={`${metrics.runningComponents}/${snapshot.components.length}`}
                detail="Query / Media / Insight / Forum / Report"
                icon={Gauge}
              />
              <MetricTile
                label="报告生成中"
                value={String(metrics.runningReports)}
                detail={`${snapshot.reportTasks.length} 个报告任务`}
                icon={BarChart3}
              />
              <MetricTile
                label="采集内容"
                value={formatNumber(metrics.crawlerNotes)}
                detail="MindSpider notes"
                icon={Database}
              />
              <MetricTile
                label="屏蔽用户"
                value={String(metrics.blockedUsers)}
                detail="跨平台黑名单规则"
                icon={Shield}
              />
            </div>
            <div className="two-column">
              <div className="flat-panel">
                <h3>组件状态</h3>
                <div className="component-list">
                  {snapshot.components.map((component) => (
                    <div className="component-row" key={component.id}>
                      <div>
                        <strong>{component.name}</strong>
                        <span>{component.message ?? "No message"}</span>
                      </div>
                      <div className="row-meta">
                        {component.lastHeartbeatAt && <span>{formatTime(component.lastHeartbeatAt)}</span>}
                        <StatusBadge value={component.status} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flat-panel">
                <h3>近期日志</h3>
                <div className="compact-log-list">
                  {snapshot.logs.slice(0, 5).map((line) => (
                    <div className="compact-log" key={line.id}>
                      <span>{formatTime(line.timestamp)}</span>
                      <strong>{line.source}</strong>
                      <p>{line.message}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>
        )}

        {activeSection === "reports" && (
          <section className="section-band">
            <SectionHeader
              title="报告任务"
              subtitle="基于多智能体输入生成 HTML、Markdown 与 PDF 报告"
              action={
                <button
                  className="primary-button"
                  onClick={() => void createReport()}
                  disabled={busyAction !== null}
                >
                  <FilePlus2 size={16} />
                  创建报告
                </button>
              }
            />
            <div className="form-grid report-form">
              <label className="field wide">
                <span>主题</span>
                <input
                  value={reportForm.topic}
                  onChange={(event) => setReportForm({ ...reportForm, topic: event.target.value })}
                  placeholder="输入报告主题"
                />
              </label>
              <label className="field">
                <span>模板</span>
                <select
                  value={reportForm.templateId}
                  onChange={(event) => setReportForm({ ...reportForm, templateId: event.target.value })}
                >
                  {snapshot.reportTemplates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="format-row">
                {(Object.keys(reportForm.formats) as ReportFormat[]).map((format) => (
                  <label key={format} className="toggle-pill">
                    <input
                      type="checkbox"
                      checked={reportForm.formats[format]}
                      onChange={(event) =>
                        setReportForm({
                          ...reportForm,
                          formats: {
                            ...reportForm.formats,
                            [format]: event.target.checked
                          }
                        })
                      }
                    />
                    <span>{format.toUpperCase()}</span>
                  </label>
                ))}
              </div>
            </div>
            {snapshot.reportTasks.length === 0 ? (
              <EmptyState title="暂无报告任务" detail="创建任务后会显示进度、状态和导出入口" />
            ) : (
              <div className="task-table">
                {snapshot.reportTasks.map((task) => (
                  <div className="task-row" key={task.id}>
                    <div className="task-main">
                      <strong>{task.topic}</strong>
                      <span>
                        {task.id} · {formatTime(task.updatedAt)}
                      </span>
                      <ProgressBar value={task.progress} />
                    </div>
                    <StatusBadge value={task.status} />
                    <div className="artifact-list">
                      {task.artifacts.map((artifact) => (
                        <a
                          key={artifact.format}
                          className={classNames("artifact-chip", !artifact.ready && "disabled")}
                          href={artifact.ready ? artifact.downloadUrl : undefined}
                          aria-disabled={!artifact.ready}
                        >
                          <Download size={14} />
                          {artifact.format}
                        </a>
                      ))}
                    </div>
                    {task.status === "running" ? (
                      <button
                        className="icon-button danger"
                        title="取消报告任务"
                        onClick={() =>
                          void runAction("报告任务已取消", async () => {
                            const updated = await cancelReportTask(task.id);
                            setSnapshot({
                              ...snapshot,
                              reportTasks: replaceReportTask(snapshot.reportTasks, updated)
                            });
                          })
                        }
                      >
                        <CircleStop size={16} />
                      </button>
                    ) : (
                      <span className="row-spacer" />
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {activeSection === "crawlers" && (
          <section className="section-band">
            <SectionHeader
              title="爬虫任务"
              subtitle="指定关键词与平台后发起 MindSpider 采集"
              action={
                <button
                  className="primary-button"
                  onClick={() => void createCrawler()}
                  disabled={busyAction !== null}
                >
                  <Play size={16} />
                  创建任务
                </button>
              }
            />
            <div className="account-panel">
              <div className="account-panel-title">
                <div>
                  <h3>爬虫账号</h3>
                  <span>{filteredCrawlerAccounts.length} / {snapshot.crawlerAccounts.length} 个账号</span>
                </div>
                <div className="account-filters">
                  <select
                    value={accountPlatformFilter}
                    aria-label="账号平台筛选"
                    onChange={(event) =>
                      setAccountPlatformFilter(event.target.value === "all" ? "all" : (event.target.value as PlatformId))
                    }
                  >
                    <option value="all">全部平台</option>
                    {snapshot.platforms.map((platform) => (
                      <option key={platform.id} value={platform.id}>
                        {platform.name}
                      </option>
                    ))}
                  </select>
                  <select
                    value={accountStatusFilter}
                    aria-label="账号状态筛选"
                    onChange={(event) =>
                      setAccountStatusFilter(
                        event.target.value === "all" ? "all" : (event.target.value as CrawlerAccountStatus)
                      )
                    }
                  >
                    <option value="all">全部状态</option>
                    <option value="active">active</option>
                    <option value="login_required">login_required</option>
                    <option value="expired">expired</option>
                    <option value="disabled">disabled</option>
                    <option value="error">error</option>
                    <option value="unknown">unknown</option>
                  </select>
                </div>
              </div>
              {filteredCrawlerAccounts.length === 0 ? (
                <EmptyState title="暂无爬虫账号" detail="账号接入后会显示平台、状态、登录方式与校验结果" />
              ) : (
                <div className="account-list">
                  {filteredCrawlerAccounts.map((account) => (
                    <div className="account-row" key={account.id}>
                      <div className="account-identity">
                        <span className="account-avatar" aria-hidden="true">
                          {account.avatarUrl ? (
                            <img src={account.avatarUrl} alt="" />
                          ) : (
                            (account.displayName ?? account.username ?? account.accountId).slice(0, 1).toUpperCase()
                          )}
                        </span>
                        <div>
                          <strong>{account.displayName ?? account.username ?? account.accountId}</strong>
                          <span>{account.username ?? account.accountId}</span>
                        </div>
                      </div>
                      <div className="account-meta">
                        <span>{platformNames[account.platformId]}</span>
                        <StatusBadge value={account.status} />
                      </div>
                      <div className="account-meta">
                        <span>{account.loginType ? loginTypeLabels[account.loginType] : "未登记"}</span>
                        <small>{account.lastCheckedAt ? formatTime(account.lastCheckedAt) : "未校验"}</small>
                      </div>
                      <div className="account-detail">
                        <strong>{account.accountId}</strong>
                        <span>{account.details?.message ?? "无附加说明"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="form-grid crawler-form">
              <label className="field wide">
                <span>关键词</span>
                <textarea
                  value={crawlerForm.keywords}
                  onChange={(event) => setCrawlerForm({ ...crawlerForm, keywords: event.target.value })}
                  placeholder="每行一个关键词"
                />
              </label>
              <label className="field">
                <span>模式</span>
                <select
                  value={crawlerForm.runMode}
                  onChange={(event) =>
                    setCrawlerForm({ ...crawlerForm, runMode: event.target.value as RunMode })
                  }
                >
                  <option value="deep_sentiment">Deep Sentiment</option>
                  <option value="full_workflow">Full Workflow</option>
                </select>
              </label>
              <label className="field">
                <span>关键词来源</span>
                <select
                  value={crawlerForm.keywordSource}
                  onChange={(event) =>
                    setCrawlerForm({
                      ...crawlerForm,
                      keywordSource: event.target.value as CrawlerTaskKeywordSource
                    })
                  }
                >
                  <option value="manual">Manual</option>
                </select>
              </label>
              <label className="field">
                <span>日期</span>
                <input
                  type="date"
                  value={crawlerForm.targetDate}
                  onChange={(event) => setCrawlerForm({ ...crawlerForm, targetDate: event.target.value })}
                />
              </label>
              <label className="field">
                <span>笔记/关键词</span>
                <input
                  type="number"
                  min={1}
                  max={1000}
                  value={crawlerForm.maxNotesPerKeyword}
                  onChange={(event) =>
                    setCrawlerForm({ ...crawlerForm, maxNotesPerKeyword: Number(event.target.value) })
                  }
                />
              </label>
              <label className="field">
                <span>评论/笔记</span>
                <input
                  type="number"
                  min={0}
                  max={5000}
                  value={crawlerForm.maxCommentsPerNote}
                  onChange={(event) =>
                    setCrawlerForm({ ...crawlerForm, maxCommentsPerNote: Number(event.target.value) })
                  }
                />
              </label>
              <label className="field">
                <span>登录方式</span>
                <select
                  value={crawlerForm.loginType}
                  onChange={(event) =>
                    setCrawlerForm({ ...crawlerForm, loginType: event.target.value as PlatformPolicy["loginType"] })
                  }
                >
                  <option value="qrcode">qrcode</option>
                  <option value="phone">phone</option>
                  <option value="cookie">cookie</option>
                </select>
              </label>
              <label className="toggle-pill headless-toggle">
                <input
                  type="checkbox"
                  checked={crawlerForm.headless}
                  onChange={(event) => setCrawlerForm({ ...crawlerForm, headless: event.target.checked })}
                />
                <span>Headless</span>
              </label>
              <div className="platform-checks">
                {snapshot.platforms.map((platform) => (
                  <label key={platform.id} className="toggle-pill">
                    <input
                      type="checkbox"
                      checked={crawlerForm.platforms.includes(platform.id)}
                      onChange={(event) =>
                        setCrawlerForm({
                          ...crawlerForm,
                          platforms: event.target.checked
                            ? [...crawlerForm.platforms, platform.id]
                            : crawlerForm.platforms.filter((id) => id !== platform.id)
                        })
                      }
                    />
                    <span>{platform.name}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="task-table">
              {snapshot.crawlerTasks.map((task) => (
                <div className="task-row crawler-row" key={task.id}>
                  <div className="task-main">
                    <strong>{task.keywords.slice(0, 3).join(" / ") || task.runMode}</strong>
                    <span>
                      {task.platforms.map((id) => platformNames[id]).join(" / ")} · {task.keywordSource} ·{" "}
                      {formatTime(task.updatedAt)}
                    </span>
                    <ProgressBar value={task.progress} />
                  </div>
                  <StatusBadge value={task.status} />
                  <div className="task-stats">
                    <span>{formatNumber(task.stats.totalNotes)} notes</span>
                    <span>{formatNumber(task.stats.totalComments)} comments</span>
                  </div>
                  {task.status === "running" ? (
                    <button
                      className="icon-button danger"
                      title="停止爬虫任务"
                      onClick={() =>
                        void runAction("爬虫任务停止中", async () => {
                          const updated = await stopCrawlerTask(task.id);
                          setSnapshot({
                            ...snapshot,
                            crawlerTasks: replaceCrawlerTask(snapshot.crawlerTasks, updated)
                          });
                        })
                      }
                    >
                      <StopCircle size={16} />
                    </button>
                  ) : (
                    <span className="row-spacer" />
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {activeSection === "platforms" && (
          <section className="section-band">
            <SectionHeader
              title="平台策略"
              subtitle="平台级爬取深度、关键词、评论数量与用户黑名单"
              action={
                <button className="primary-button" onClick={() => void savePolicy()} disabled={!policyDraft}>
                  <Save size={16} />
                  保存策略
                </button>
              }
            />
            <div className="platform-layout">
              <div className="platform-list">
                {snapshot.platforms.map((platform) => (
                  <button
                    key={platform.id}
                    className={classNames("platform-button", selectedPlatformId === platform.id && "active")}
                    onClick={() => setSelectedPlatformId(platform.id)}
                  >
                    <strong>{platform.name}</strong>
                    <span>
                      黑名单 {platform.identityRuleCounts.block}
                    </span>
                  </button>
                ))}
              </div>

              {selectedPlatform && policyDraft && (
                <div className="policy-editor">
                  <div className="policy-title">
                    <div>
                      <h3>{selectedPlatform.name}</h3>
                      <span>{selectedPlatform.id} / {selectedPlatform.crawlerType}</span>
                    </div>
                    <label className="switch">
                      <input
                        type="checkbox"
                        checked={policyDraft.enabled}
                        onChange={(event) => setPolicyValue("enabled", event.target.checked)}
                      />
                      <span />
                    </label>
                  </div>
                  <div className="form-grid policy-grid">
                    <label className="field">
                      <span>爬取深度</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={policyDraft.crawlDepth}
                        onChange={(event) => setPolicyValue("crawlDepth", Number(event.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span>关键词上限</span>
                      <input
                        type="number"
                        min={1}
                        max={500}
                        value={policyDraft.maxKeywords}
                        onChange={(event) => setPolicyValue("maxKeywords", Number(event.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span>笔记/关键词</span>
                      <input
                        type="number"
                        min={1}
                        max={1000}
                        value={policyDraft.maxNotesPerKeyword}
                        onChange={(event) => setPolicyValue("maxNotesPerKeyword", Number(event.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span>评论/笔记</span>
                      <input
                        type="number"
                        min={0}
                        max={5000}
                        value={policyDraft.maxCommentsPerNote}
                        onChange={(event) => setPolicyValue("maxCommentsPerNote", Number(event.target.value))}
                      />
                    </label>
                    <label className="field">
                      <span>频率</span>
                      <select
                        value={policyDraft.frequency.mode}
                        onChange={(event) =>
                          setPolicyValue("frequency", {
                            ...policyDraft.frequency,
                            mode: event.target.value as PlatformPolicy["frequency"]["mode"]
                          })
                        }
                      >
                        <option value="manual">manual</option>
                        <option value="hourly">hourly</option>
                        <option value="daily">daily</option>
                        <option value="weekly">weekly</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>登录方式</span>
                      <select
                        value={policyDraft.loginType}
                        onChange={(event) =>
                          setPolicyValue("loginType", event.target.value as PlatformPolicy["loginType"])
                        }
                      >
                        <option value="qrcode">qrcode</option>
                        <option value="phone">phone</option>
                        <option value="cookie">cookie</option>
                      </select>
                    </label>
                    <label className="field wide">
                      <span>关键词</span>
                      <textarea
                        value={policyDraft.keywords.join("\n")}
                        onChange={(event) =>
                          setPolicyValue(
                            "keywords",
                            event.target.value
                              .split("\n")
                              .map((item) => item.trim())
                              .filter(Boolean)
                          )
                        }
                      />
                    </label>
                  </div>
                  <div className="identity-manager">
                    <h3>用户黑名单</h3>
                    <div className="identity-form">
                      <input
                        value={identityForm.userId}
                        onChange={(event) => setIdentityForm({ ...identityForm, userId: event.target.value })}
                        placeholder="平台用户 ID"
                      />
                      <input
                        value={identityForm.label}
                        onChange={(event) => setIdentityForm({ ...identityForm, label: event.target.value })}
                        placeholder="标签"
                      />
                      <button className="secondary-button" onClick={() => void addIdentity()}>
                        <Shield size={16} />
                        添加黑名单
                      </button>
                    </div>
                    {selectedLegacyAllowRuleCount > 0 && (
                      <p className="identity-legacy-note">
                        已忽略 {selectedLegacyAllowRuleCount} 条历史白名单规则，白名单不参与爬虫过滤。
                      </p>
                    )}
                    {selectedRules.length === 0 ? (
                      <EmptyState title="暂无黑名单规则" detail="黑名单规则会在日过滤后、入库前排除匹配用户内容" />
                    ) : (
                      <div className="rule-list">
                        {selectedRules.map((rule) => (
                          <div className="rule-row" key={rule.id}>
                            <span className="status-badge tone-bad">黑名单</span>
                            <div>
                              <strong>{rule.userId}</strong>
                              <span>{rule.label || rule.reason || "未填写说明"}</span>
                            </div>
                            <button
                              className="icon-button danger"
                              title="删除黑名单规则"
                              onClick={() => void removeIdentity(rule)}
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {activeSection === "config" && (
          <section className="section-band">
            <SectionHeader
              title="系统配置"
              subtitle="LLM、搜索、数据库与爬虫运行参数"
              action={
                <button className="primary-button" onClick={() => void saveConfig()}>
                  <Save size={16} />
                  保存配置
                </button>
              }
            />
            <div className="config-groups">
              {(["server", "database", "llm", "search", "crawler"] as ConfigField["group"][]).map((group) => {
                const fields = snapshot.configFields.filter((field) => field.group === group);
                if (fields.length === 0) return null;
                return (
                  <div className="config-group" key={group}>
                    <h3>{group}</h3>
                    <div className="config-grid">
                      {fields.map((field) => {
                        const value = configDraft[field.key] ?? (field.sensitive ? "" : field.value);
                        return (
                          <label className="field" key={field.key}>
                            <span>
                              {field.sensitive && <LockKeyhole size={14} />}
                              {field.label}
                            </span>
                            {field.type === "enum" ? (
                              <select
                                value={value}
                                onChange={(event) =>
                                  setConfigDraft({ ...configDraft, [field.key]: event.target.value })
                                }
                              >
                                {field.options?.map((option) => (
                                  <option key={option} value={option}>
                                    {option}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                type={field.sensitive ? "password" : field.type === "number" ? "number" : "text"}
                                value={value}
                                placeholder={field.sensitive ? field.value : ""}
                                onChange={(event) =>
                                  setConfigDraft({ ...configDraft, [field.key]: event.target.value })
                                }
                              />
                            )}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {activeSection === "logs" && (
          <section className="section-band">
            <SectionHeader
              title="运行日志"
              subtitle="按来源查看系统、引擎、报告和爬虫日志"
              action={
                <label className="filter-control">
                  <Filter size={16} />
                  <select value={logSource} onChange={(event) => setLogSource(event.target.value)}>
                    <option value="all">all</option>
                    <option value="system">system</option>
                    <option value="query">query</option>
                    <option value="media">media</option>
                    <option value="insight">insight</option>
                    <option value="forum">forum</option>
                    <option value="report">report</option>
                    <option value="crawler">crawler</option>
                  </select>
                </label>
              }
            />
            {filteredLogs.length === 0 ? (
              <EmptyState title="没有匹配日志" detail="调整来源筛选后再查看" />
            ) : (
              <div className="log-table">
                {filteredLogs.map((line) => (
                  <div className="log-row" key={line.id}>
                    <span>{formatTime(line.timestamp)}</span>
                    <StatusBadge value={line.level === "error" ? "failed" : line.level === "warning" ? "queued" : "running"} />
                    <strong>{line.source}</strong>
                    <p>{line.message}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}
      </main>

      {busyAction && (
        <div className="busy-overlay" role="status">
          <Loader2 className="spin" size={18} />
          <span>{busyAction}</span>
        </div>
      )}
    </div>
  );
}
