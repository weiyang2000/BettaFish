"""SQLite persistence for the SaaS service layer.

The service layer intentionally owns its own task/config tables instead of
reusing the legacy Flask globals. This gives the new API durable state while
the engine and crawler adapters can evolve independently.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
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

CREATE INDEX IF NOT EXISTS idx_report_tasks_workspace
    ON report_tasks(workspace_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_crawler_tasks_workspace
    ON crawler_tasks(workspace_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_identity_rules_platform
    ON crawler_identity_rules(workspace_id, platform_id, list_type);

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

CREATE INDEX IF NOT EXISTS idx_crawler_strategies_workspace
    ON crawler_strategies(workspace_id, created_at DESC);

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

CREATE INDEX IF NOT EXISTS idx_task_events_task
    ON task_events(workspace_id, task_id, id);

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
"""


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class Store:
    """Small SQLite repository used by FastAPI route handlers and tests."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            self._ensure_column(
                conn,
                "crawler_tasks",
                "keywords_json",
                "TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                conn,
                "crawler_tasks",
                "keyword_source",
                "TEXT NOT NULL DEFAULT 'manual'",
            )
            self._ensure_column(
                conn,
                "crawler_tasks",
                "max_notes_per_keyword",
                "INTEGER NOT NULL DEFAULT 50",
            )
            self._ensure_column(
                conn,
                "crawler_tasks",
                "max_comments_per_note",
                "INTEGER NOT NULL DEFAULT 100",
            )
            self._ensure_column(
                conn,
                "crawler_tasks",
                "login_type",
                "TEXT",
            )
            self._ensure_column(
                conn,
                "crawler_tasks",
                "headless",
                "INTEGER NOT NULL DEFAULT 1",
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def execute(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> None:
        with self._connect() as conn:
            conn.execute(sql, tuple(params))
            conn.commit()

    def execute_returning_row(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            conn.commit()
            return dict(row) if row else None

    def query_one(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def query_all(
        self,
        sql: str,
        params: Iterable[Any] = (),
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
