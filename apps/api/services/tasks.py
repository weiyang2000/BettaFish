"""Task lifecycle services for reports, crawlers, and search runs."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from apps.api.schemas import (
    ApiError,
    CreateCrawlerTaskRequest,
    CreateReportTaskRequest,
    CrawlerStrategyInput,
    REPORT_FORMATS,
    UserRef,
)
from apps.api.services.common import new_id, slugify_filename, utc_now
from apps.api.services.platforms import load_active_block_rules
from apps.api.storage import Store, dumps, loads


TERMINAL_REPORT_STATUSES = {"succeeded", "failed", "cancelled"}
TERMINAL_CRAWLER_STATUSES = {"succeeded", "failed", "stopped", "cancelled"}
CRAWLER_ADAPTER_ENV = "BETTAFISH_API_CRAWLER_ADAPTER"


class TaskService:
    def __init__(self, store: Store, artifact_dir: Path, run_workers: bool = False):
        self.store = store
        self.artifact_dir = artifact_dir
        self.run_workers = run_workers
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def create_search_run(
        self,
        workspace_id: str,
        query: str,
        engines: list[str],
        owner: UserRef | None,
    ) -> dict[str, Any]:
        run_id = new_id("search")
        created_at = utc_now()
        self.store.execute(
            """
            INSERT INTO search_runs (
                id, workspace_id, query, status, engines_json, owner_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                workspace_id,
                query,
                "queued",
                dumps(engines),
                self._user_json(owner),
                created_at,
            ),
        )
        return {
            "id": run_id,
            "workspaceId": workspace_id,
            "query": query,
            "status": "queued",
            "engines": engines,
            "createdAt": created_at,
            **self._optional_user("owner", owner),
        }

    def create_report_task(
        self,
        workspace_id: str,
        payload: CreateReportTaskRequest,
    ) -> dict[str, Any]:
        task_id = new_id("report")
        now = utc_now()
        formats = payload.outputFormats or ["html"]
        artifacts = [
            {
                "format": item,
                "ready": False,
                "downloadUrl": f"/api/v1/report-tasks/{task_id}/exports/{item}",
            }
            for item in formats
        ]
        self.store.execute(
            """
            INSERT INTO report_tasks (
                id, workspace_id, topic, status, progress, stage, template_id,
                source_scope_json, output_formats_json, artifacts_json,
                owner_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                workspace_id,
                payload.topic,
                "queued",
                0,
                "queued",
                payload.templateId,
                dumps(payload.sourceScope.model_dump(mode="json")),
                dumps(formats),
                dumps(artifacts),
                self._user_json(payload.owner),
                now,
                now,
            ),
        )
        task = self.get_report_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "report", "status", {"task": task})
        if self.run_workers:
            threading.Thread(
                target=self._run_stub_report,
                args=(workspace_id, task_id),
                daemon=True,
            ).start()
        return task

    def list_report_tasks(
        self,
        workspace_id: str,
        status: str | None,
        page_size: int,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [workspace_id]
        where = "workspace_id = ?"
        if status:
            where += " AND status = ?"
            params.append(status)
        params.append(page_size)
        rows = self.store.query_all(
            f"""
            SELECT *
            FROM report_tasks
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )
        return [self._report_row(row) for row in rows]

    def get_report_task(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        row = self.store.query_one(
            "SELECT * FROM report_tasks WHERE workspace_id = ? AND id = ?",
            (workspace_id, task_id),
        )
        if not row:
            raise ApiError("NOT_FOUND", "Report task not found", status_code=404)
        return self._report_row(row)

    def cancel_report_task(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        task = self.get_report_task(workspace_id, task_id)
        if task["status"] in TERMINAL_REPORT_STATUSES:
            raise ApiError(
                "TASK_NOT_CANCELLABLE",
                "Report task is already terminal",
                status_code=409,
            )
        now = utc_now()
        error = {
            "success": False,
            "error": {
                "code": "TASK_NOT_CANCELLABLE",
                "message": "Task cancelled by user",
            },
        }
        self.store.execute(
            """
            UPDATE report_tasks
            SET status = 'cancelled', progress = progress, stage = 'failed',
                error_json = ?, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (dumps(error), now, workspace_id, task_id),
        )
        task = self.get_report_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "report", "cancelled", {"task": task})
        return task

    def get_report_result(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        task = self.get_report_task(workspace_id, task_id)
        if task["status"] != "succeeded":
            raise ApiError(
                "EXPORT_UNAVAILABLE",
                "Report result is not ready",
                status_code=409,
                details={"status": task["status"]},
            )
        html_path = self.artifact_path(task_id, "html")
        html_content = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        return {
            "success": True,
            "taskId": task_id,
            "htmlPreviewUrl": f"/api/v1/report-tasks/{task_id}/exports/html",
            "htmlContent": html_content,
            "artifacts": task.get("artifacts", []),
        }

    def artifact_path(self, task_id: str, report_format: str) -> Path:
        if report_format not in REPORT_FORMATS:
            raise ApiError("VALIDATION_ERROR", "Unsupported report format", status_code=400)
        suffix = "json" if report_format == "json" else report_format
        return self.artifact_dir / f"{task_id}.{suffix}"

    def add_event(
        self,
        workspace_id: str,
        task_id: str,
        task_type: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        created_at = utc_now()
        row = self.store.execute_returning_row(
            """
            INSERT INTO task_events (
                workspace_id, task_id, task_type, event_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id, event_type, payload_json, created_at
            """,
            (workspace_id, task_id, task_type, event_type, dumps(payload), created_at),
        )
        return self._event_row(task_id, row)

    def list_events(self, workspace_id: str, task_id: str, after_id: int | None = None) -> list[dict[str, Any]]:
        params: list[Any] = [workspace_id, task_id]
        where = "workspace_id = ? AND task_id = ?"
        if after_id is not None:
            where += " AND id > ?"
            params.append(after_id)
        rows = self.store.query_all(
            f"""
            SELECT id, event_type, payload_json, created_at
            FROM task_events
            WHERE {where}
            ORDER BY id ASC
            """,
            params,
        )
        return [self._event_row(task_id, row) for row in rows]

    def create_crawler_strategy(
        self,
        workspace_id: str,
        payload: CrawlerStrategyInput,
    ) -> dict[str, Any]:
        strategy_id = new_id("strategy")
        now = utc_now()
        policies = [
            policy.to_policy(policy.platformId, now) for policy in payload.platformPolicies
        ]
        self.store.execute(
            """
            INSERT INTO crawler_strategies (
                id, workspace_id, name, run_mode, platform_policies_json,
                owner_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_id,
                workspace_id,
                payload.name,
                payload.runMode,
                dumps(policies),
                self._user_json(payload.owner),
                now,
                now,
            ),
        )
        return self.get_crawler_strategy(workspace_id, strategy_id)

    def list_crawler_strategies(self, workspace_id: str) -> list[dict[str, Any]]:
        rows = self.store.query_all(
            """
            SELECT *
            FROM crawler_strategies
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            """,
            (workspace_id,),
        )
        return [self._strategy_row(row) for row in rows]

    def get_crawler_strategy(self, workspace_id: str, strategy_id: str) -> dict[str, Any]:
        row = self.store.query_one(
            "SELECT * FROM crawler_strategies WHERE workspace_id = ? AND id = ?",
            (workspace_id, strategy_id),
        )
        if not row:
            raise ApiError("NOT_FOUND", "Crawler strategy not found", status_code=404)
        return self._strategy_row(row)

    def create_crawler_task(
        self,
        workspace_id: str,
        payload: CreateCrawlerTaskRequest,
    ) -> dict[str, Any]:
        task_id = new_id("crawler")
        now = utc_now()
        stats = {
            "totalKeywords": len(payload.keywords),
            "totalPlatforms": len(payload.platforms),
            "totalTasks": len(payload.keywords) * len(payload.platforms),
            "successfulTasks": 0,
            "failedTasks": 0,
            "totalNotes": 0,
            "totalComments": 0,
            "filteredNotes": 0,
            "filteredComments": 0,
            "platformSummary": {},
        }
        self.store.execute(
            """
            INSERT INTO crawler_tasks (
                id, workspace_id, strategy_id, run_mode, target_date,
                platforms_json, keywords_json, keyword_source,
                max_notes_per_keyword, max_comments_per_note, login_type,
                headless, overrides_json, status, progress, stats_json,
                owner_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                workspace_id,
                payload.strategyId,
                payload.runMode,
                payload.targetDate,
                dumps(payload.platforms),
                dumps(payload.keywords),
                payload.keywordSource,
                payload.maxNotesPerKeyword
                if payload.maxNotesPerKeyword is not None
                else 50,
                payload.maxCommentsPerNote
                if payload.maxCommentsPerNote is not None
                else 100,
                payload.loginType,
                1 if payload.headless is not False else 0,
                dumps([item.model_dump(mode="json") for item in payload.overrides]),
                "queued",
                0,
                dumps(stats),
                self._user_json(payload.owner),
                now,
                now,
            ),
        )
        task = self.get_crawler_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "crawler", "status", {"task": task})
        if self.run_workers:
            threading.Thread(
                target=self._run_crawler_worker,
                args=(workspace_id, task_id),
                daemon=True,
            ).start()
        return task

    def list_crawler_tasks(
        self,
        workspace_id: str,
        status: str | None,
        platform: str | None,
        page_size: int,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [workspace_id]
        filters = ["workspace_id = ?"]
        if status:
            filters.append("status = ?")
            params.append(status)
        if platform:
            filters.append(
                """
                EXISTS (
                    SELECT 1
                    FROM json_each(crawler_tasks.platforms_json)
                    WHERE json_each.value = ?
                )
                """
            )
            params.append(platform)
        params.append(page_size)
        rows = self.store.query_all(
            """
            SELECT *
            FROM crawler_tasks
            WHERE """ + " AND ".join(filters) + """
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        )
        return [self._crawler_row(row) for row in rows]

    def get_crawler_task(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        row = self.store.query_one(
            "SELECT * FROM crawler_tasks WHERE workspace_id = ? AND id = ?",
            (workspace_id, task_id),
        )
        if not row:
            raise ApiError("NOT_FOUND", "Crawler task not found", status_code=404)
        return self._crawler_row(row)

    def stop_crawler_task(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        task = self.get_crawler_task(workspace_id, task_id)
        if task["status"] in TERMINAL_CRAWLER_STATUSES:
            raise ApiError(
                "TASK_NOT_CANCELLABLE",
                "Crawler task is already terminal",
                status_code=409,
            )
        now = utc_now()
        self.store.execute(
            """
            UPDATE crawler_tasks
            SET status = 'stopped', progress = progress, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (now, workspace_id, task_id),
        )
        task = self.get_crawler_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "crawler", "stopped", {"task": task})
        return task

    def retry_crawler_task(self, workspace_id: str, task_id: str) -> dict[str, Any]:
        task = self.get_crawler_task(workspace_id, task_id)
        if task["status"] not in {"failed", "stopped", "cancelled"}:
            raise ApiError(
                "CONFLICT",
                "Only failed, stopped, or cancelled crawler tasks can be retried",
                status_code=409,
            )
        now = utc_now()
        self.store.execute(
            """
            UPDATE crawler_tasks
            SET status = 'queued', progress = 0, error_json = NULL, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (now, workspace_id, task_id),
        )
        task = self.get_crawler_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "crawler", "status", {"task": task})
        return task

    def _run_stub_report(self, workspace_id: str, task_id: str) -> None:
        stages = [
            ("running", 12, "prepare"),
            ("running", 45, "agent_running"),
            ("running", 85, "persist"),
        ]
        for status, progress, stage in stages:
            if self.get_report_task(workspace_id, task_id)["status"] == "cancelled":
                return
            time.sleep(0.05)
            now = utc_now()
            self.store.execute(
                """
                UPDATE report_tasks
                SET status = ?, progress = ?, stage = ?, updated_at = ?
                WHERE workspace_id = ? AND id = ?
                """,
                (status, progress, stage, now, workspace_id, task_id),
            )
            self.add_event(
                workspace_id,
                task_id,
                "report",
                "progress",
                {"status": status, "progress": progress, "stage": stage},
            )
        self._write_stub_report_artifacts(workspace_id, task_id)

    def _write_stub_report_artifacts(self, workspace_id: str, task_id: str) -> None:
        task = self.get_report_task(workspace_id, task_id)
        safe_topic = slugify_filename(task["topic"], "report")
        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{task['topic']}</title></head><body>"
            f"<h1>{task['topic']}</h1><p>BettaFish SaaS report placeholder.</p>"
            "</body></html>"
        )
        md = f"# {task['topic']}\n\nBettaFish SaaS report placeholder.\n"
        json_content = dumps({"taskId": task_id, "topic": task["topic"], "status": "succeeded"})
        files = {"html": html, "md": md, "json": json_content, "pdf": ""}
        formats = loads(
            self.store.query_one(
                "SELECT output_formats_json FROM report_tasks WHERE id = ?",
                (task_id,),
            )["output_formats_json"],
            ["html"],
        )
        artifacts = []
        for report_format in formats:
            path = self.artifact_path(task_id, report_format)
            content = files[report_format]
            if report_format == "pdf":
                path.write_bytes(b"%PDF-1.4\n% BettaFish placeholder PDF\n")
            else:
                path.write_text(content, encoding="utf-8")
            artifacts.append(
                {
                    "format": report_format,
                    "ready": True,
                    "filename": f"{safe_topic}.{report_format}",
                    "sizeBytes": path.stat().st_size,
                    "downloadUrl": f"/api/v1/report-tasks/{task_id}/exports/{report_format}",
                }
            )
        now = utc_now()
        self.store.execute(
            """
            UPDATE report_tasks
            SET status = 'succeeded', progress = 100, stage = 'completed',
                artifacts_json = ?, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (dumps(artifacts), now, workspace_id, task_id),
        )
        task = self.get_report_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "report", "completed", {"task": task})

    def _run_crawler_worker(self, workspace_id: str, task_id: str) -> None:
        task = self.get_crawler_task(workspace_id, task_id)
        if task["status"] in TERMINAL_CRAWLER_STATUSES:
            return
        self._mark_crawler_running(workspace_id, task_id)

        adapter_mode = os.getenv(CRAWLER_ADAPTER_ENV, "stub").lower()
        if adapter_mode not in {"auto", "real", "stub"}:
            adapter_mode = "stub"

        if adapter_mode in {"auto", "real"}:
            try:
                stats = self._run_real_crawler(task)
                self._complete_crawler_task(workspace_id, task_id, stats)
                return
            except Exception as exc:
                if adapter_mode == "real":
                    self._fail_crawler_task(workspace_id, task_id, exc)
                    return

        stats = self._stub_crawler_stats(task)
        self._complete_crawler_task(workspace_id, task_id, stats)

    def _mark_crawler_running(self, workspace_id: str, task_id: str) -> None:
        now = utc_now()
        self.store.execute(
            """
            UPDATE crawler_tasks
            SET status = 'running', progress = 10, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (now, workspace_id, task_id),
        )
        task = self.get_crawler_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "crawler", "progress", {"task": task})

    def _run_real_crawler(self, task: dict[str, Any]) -> dict[str, Any]:
        from MindSpider.DeepSentimentCrawling.platform_crawler import PlatformCrawler

        crawler = PlatformCrawler()
        block_rules_by_platform = self._load_crawler_block_rules(task)
        result = crawler.run_multi_platform_crawl_by_keywords(
            task["keywords"],
            task["platforms"],
            login_type=task.get("loginType") or "qrcode",
            max_notes_per_keyword=task.get("maxNotesPerKeyword") or 50,
            block_rules_by_platform=block_rules_by_platform,
        )
        return self._real_crawler_stats_to_api(result)

    def _load_crawler_block_rules(
        self,
        task: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        workspace_id = task.get("workspaceId")
        platforms = task.get("platforms", [])
        if not workspace_id or not platforms:
            return {platform: [] for platform in platforms}
        return load_active_block_rules(self.store, workspace_id, platforms)

    @staticmethod
    def _real_crawler_stats_to_api(result: dict[str, Any]) -> dict[str, Any]:
        platform_summary = {}
        for platform, summary in result.get("platform_summary", {}).items():
            platform_summary[platform] = {
                "successfulKeywords": summary.get("successful_keywords", 0),
                "failedKeywords": summary.get("failed_keywords", 0),
                "totalNotes": summary.get("total_notes", 0),
                "totalComments": summary.get("total_comments", 0),
                "filteredNotes": summary.get("filtered_notes", 0),
                "filteredComments": summary.get("filtered_comments", 0),
            }
        filtered_notes = result.get(
            "filtered_notes",
            sum(item["filteredNotes"] for item in platform_summary.values()),
        )
        filtered_comments = result.get(
            "filtered_comments",
            sum(item["filteredComments"] for item in platform_summary.values()),
        )
        return {
            "totalKeywords": result.get("total_keywords", 0),
            "totalPlatforms": result.get("total_platforms", 0),
            "totalTasks": result.get("total_tasks", 0),
            "successfulTasks": result.get("successful_tasks", 0),
            "failedTasks": result.get("failed_tasks", 0),
            "totalNotes": result.get("total_notes", 0),
            "totalComments": result.get("total_comments", 0),
            "filteredNotes": filtered_notes,
            "filteredComments": filtered_comments,
            "platformSummary": platform_summary,
        }

    @staticmethod
    def _stub_crawler_stats(task: dict[str, Any]) -> dict[str, Any]:
        platforms = task["platforms"]
        total_keywords = len(task.get("keywords", []))
        time.sleep(0.05)
        total_tasks = total_keywords * len(platforms)
        return {
            "totalKeywords": total_keywords,
            "totalPlatforms": len(platforms),
            "totalTasks": total_tasks,
            "successfulTasks": total_tasks,
            "failedTasks": 0,
            "totalNotes": total_tasks * 10,
            "totalComments": total_tasks * 50,
            "filteredNotes": 0,
            "filteredComments": 0,
            "platformSummary": {
                platform: {
                    "successfulKeywords": total_keywords,
                    "failedKeywords": 0,
                    "totalNotes": total_keywords * 10,
                    "totalComments": total_keywords * 50,
                    "filteredNotes": 0,
                    "filteredComments": 0,
                }
                for platform in platforms
            },
        }

    def _complete_crawler_task(
        self,
        workspace_id: str,
        task_id: str,
        stats: dict[str, Any],
    ) -> None:
        now = utc_now()
        self.store.execute(
            """
            UPDATE crawler_tasks
            SET status = 'succeeded', progress = 100, stats_json = ?, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (dumps(stats), now, workspace_id, task_id),
        )
        task = self.get_crawler_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "crawler", "completed", {"task": task})

    def _fail_crawler_task(
        self,
        workspace_id: str,
        task_id: str,
        exc: Exception,
    ) -> None:
        now = utc_now()
        error = {
            "success": False,
            "error": {
                "code": "CRAWLER_ADAPTER_FAILED",
                "message": str(exc),
            },
        }
        self.store.execute(
            """
            UPDATE crawler_tasks
            SET status = 'failed', progress = 100, error_json = ?, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (dumps(error), now, workspace_id, task_id),
        )
        task = self.get_crawler_task(workspace_id, task_id)
        self.add_event(workspace_id, task_id, "crawler", "failed", {"task": task})

    def _report_row(self, row: dict[str, Any]) -> dict[str, Any]:
        task = {
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "tenantId": row["tenant_id"],
            "legacyTaskId": row["legacy_task_id"],
            "topic": row["topic"],
            "status": row["status"],
            "progress": row["progress"],
            "stage": row["stage"],
            "templateId": row["template_id"],
            "sourceScope": loads(row["source_scope_json"], {}),
            "artifacts": loads(row["artifacts_json"], []),
            "error": loads(row["error_json"], None),
            "owner": loads(row["owner_json"], None),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        return {key: value for key, value in task.items() if value is not None}

    def _crawler_row(self, row: dict[str, Any]) -> dict[str, Any]:
        task = {
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "tenantId": row["tenant_id"],
            "strategyId": row["strategy_id"],
            "runMode": row["run_mode"],
            "targetDate": row["target_date"],
            "platforms": loads(row["platforms_json"], []),
            "keywords": loads(row["keywords_json"], []),
            "keywordSource": row["keyword_source"],
            "maxNotesPerKeyword": row["max_notes_per_keyword"],
            "maxCommentsPerNote": row["max_comments_per_note"],
            "loginType": row["login_type"],
            "headless": bool(row["headless"]),
            "status": row["status"],
            "progress": row["progress"],
            "stats": loads(row["stats_json"], {}),
            "error": loads(row["error_json"], None),
            "owner": loads(row["owner_json"], None),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        return {key: value for key, value in task.items() if value is not None}

    def _strategy_row(self, row: dict[str, Any]) -> dict[str, Any]:
        strategy = {
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "tenantId": row["tenant_id"],
            "name": row["name"],
            "runMode": row["run_mode"],
            "platformPolicies": loads(row["platform_policies_json"], []),
            "owner": loads(row["owner_json"], None),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        return {key: value for key, value in strategy.items() if value is not None}

    @staticmethod
    def _event_row(task_id: str, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise ApiError("INTERNAL_ERROR", "Failed to persist task event", status_code=500)
        return {
            "id": str(row["id"]),
            "type": row["event_type"],
            "taskId": task_id,
            "timestamp": row["created_at"],
            "payload": loads(row["payload_json"], {}),
        }

    @staticmethod
    def _user_json(user: UserRef | None) -> str | None:
        return dumps(user.model_dump(exclude_none=True)) if user else None

    @staticmethod
    def _optional_user(key: str, user: UserRef | None) -> dict[str, Any]:
        return {key: user.model_dump(exclude_none=True)} if user else {}
