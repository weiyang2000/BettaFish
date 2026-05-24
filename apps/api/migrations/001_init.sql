-- BettaFish SaaS service-layer persistence.
-- The FastAPI app applies the equivalent schema automatically on startup.
-- Keep this file as the human-reviewable migration plan for production DBs.

CREATE TABLE IF NOT EXISTS report_tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    tenant_id TEXT,
    legacy_task_id TEXT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT 'queued',
    template_id TEXT,
    source_scope_json TEXT NOT NULL DEFAULT '{}',
    output_formats_json TEXT NOT NULL DEFAULT '[]',
    artifacts_json TEXT NOT NULL DEFAULT '[]',
    error_json TEXT,
    owner_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawler_tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    tenant_id TEXT,
    strategy_id TEXT,
    run_mode TEXT NOT NULL,
    target_date TEXT,
    platforms_json TEXT NOT NULL DEFAULT '[]',
    keywords_json TEXT NOT NULL DEFAULT '[]',
    keyword_source TEXT NOT NULL DEFAULT 'manual',
    max_notes_per_keyword INTEGER NOT NULL DEFAULT 50,
    max_comments_per_note INTEGER NOT NULL DEFAULT 100,
    login_type TEXT,
    headless INTEGER NOT NULL DEFAULT 1,
    overrides_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    stats_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT,
    owner_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawler_accounts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    username TEXT,
    display_name TEXT,
    avatar_url TEXT,
    profile_url TEXT,
    status TEXT NOT NULL,
    login_type TEXT,
    last_login_at TEXT,
    last_checked_at TEXT,
    details_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, platform_id, account_id)
);

CREATE INDEX IF NOT EXISTS idx_crawler_accounts_workspace
    ON crawler_accounts(workspace_id, platform_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS crawler_platform_configs (
    workspace_id TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    crawl_depth INTEGER NOT NULL,
    max_keywords INTEGER NOT NULL,
    max_notes_per_keyword INTEGER NOT NULL,
    max_comments_per_note INTEGER NOT NULL,
    keywords_json TEXT NOT NULL DEFAULT '[]',
    keyword_source TEXT NOT NULL,
    frequency_json TEXT NOT NULL DEFAULT '{}',
    login_type TEXT NOT NULL,
    headless INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_json TEXT,
    PRIMARY KEY (workspace_id, platform_id)
);

CREATE TABLE IF NOT EXISTS crawler_identity_rules (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    list_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    label TEXT,
    reason TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    created_by_json TEXT,
    UNIQUE (workspace_id, platform_id, list_type, user_id)
);

CREATE TABLE IF NOT EXISTS crawler_strategies (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    tenant_id TEXT,
    name TEXT NOT NULL,
    run_mode TEXT NOT NULL,
    platform_policies_json TEXT NOT NULL DEFAULT '[]',
    owner_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_configs (
    workspace_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value_json TEXT,
    sensitive INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    updated_by_json TEXT,
    PRIMARY KEY (workspace_id, key)
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_runs (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    tenant_id TEXT,
    query TEXT NOT NULL,
    status TEXT NOT NULL,
    engines_json TEXT NOT NULL DEFAULT '[]',
    owner_json TEXT,
    created_at TEXT NOT NULL
);
