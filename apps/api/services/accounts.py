"""Crawler account persistence and sensitive-field filtering."""

from __future__ import annotations

from typing import Any

from apps.api.schemas import (
    CRAWLER_ACCOUNT_STATUSES,
    ApiError,
    CrawlerAccountUpsertRequest,
    PLATFORM_IDS,
)
from apps.api.services.common import new_id, utc_now
from apps.api.storage import Store, dumps, loads


SENSITIVE_DETAIL_KEYS = {
    "auth",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
    "access_token",
}


class AccountService:
    def __init__(self, store: Store):
        self.store = store

    def list_accounts(
        self,
        workspace_id: str,
        platform_id: str | None = None,
        status: str | None = None,
        page_size: int = 50,
    ) -> list[dict[str, Any]]:
        if platform_id:
            self._ensure_platform(platform_id)
        if status and status not in CRAWLER_ACCOUNT_STATUSES:
            raise ApiError(
                "VALIDATION_ERROR",
                "Unsupported crawler account status",
                status_code=400,
            )

        filters = ["workspace_id = ?"]
        params: list[Any] = [workspace_id]
        if platform_id:
            filters.append("platform_id = ?")
            params.append(platform_id)
        if status:
            filters.append("status = ?")
            params.append(status)
        params.append(page_size)

        rows = self.store.query_all(
            f"""
            SELECT *
            FROM crawler_accounts
            WHERE {' AND '.join(filters)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            params,
        )
        return [self._account_row(row) for row in rows]

    def upsert_account(
        self,
        workspace_id: str,
        account_id: str,
        payload: CrawlerAccountUpsertRequest,
    ) -> dict[str, Any]:
        self._ensure_platform(payload.platformId)

        details = self.sanitize_details(payload.details)
        error = self.sanitize_details(payload.error) if payload.error else None
        now = utc_now()
        existing = self.store.query_one(
            """
            SELECT id, created_at
            FROM crawler_accounts
            WHERE workspace_id = ? AND platform_id = ? AND account_id = ?
            """,
            (workspace_id, payload.platformId, account_id),
        )
        row_id = existing["id"] if existing else new_id("account")
        created_at = existing["created_at"] if existing else now
        last_checked_at = payload.lastCheckedAt or now

        self.store.execute(
            """
            INSERT INTO crawler_accounts (
                id, workspace_id, platform_id, account_id, username, display_name,
                avatar_url, profile_url, status, login_type, last_login_at,
                last_checked_at, details_json, error_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, platform_id, account_id) DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name,
                avatar_url = excluded.avatar_url,
                profile_url = excluded.profile_url,
                status = excluded.status,
                login_type = excluded.login_type,
                last_login_at = excluded.last_login_at,
                last_checked_at = excluded.last_checked_at,
                details_json = excluded.details_json,
                error_json = excluded.error_json,
                updated_at = excluded.updated_at
            """,
            (
                row_id,
                workspace_id,
                payload.platformId,
                account_id,
                payload.username,
                payload.displayName,
                payload.avatarUrl,
                payload.profileUrl,
                payload.status,
                payload.loginType,
                payload.lastLoginAt,
                last_checked_at,
                dumps(details),
                dumps(error) if error else None,
                created_at,
                now,
            ),
        )
        row = self.store.query_one(
            """
            SELECT *
            FROM crawler_accounts
            WHERE workspace_id = ? AND platform_id = ? AND account_id = ?
            """,
            (workspace_id, payload.platformId, account_id),
        )
        return self._account_row(row)

    def account_counts(self, workspace_id: str, platform_id: str) -> dict[str, int]:
        self._ensure_platform(platform_id)
        rows = self.store.query_all(
            """
            SELECT status, COUNT(*) AS count
            FROM crawler_accounts
            WHERE workspace_id = ? AND platform_id = ?
            GROUP BY status
            """,
            (workspace_id, platform_id),
        )
        counts = {
            "active": 0,
            "loginRequired": 0,
            "expired": 0,
            "disabled": 0,
            "error": 0,
            "unknown": 0,
        }
        for row in rows:
            key = "loginRequired" if row["status"] == "login_required" else row["status"]
            counts[key] = row["count"]
        return counts

    @staticmethod
    def sanitize_details(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}

        def sanitize(item: Any) -> Any:
            if isinstance(item, dict):
                cleaned = {}
                for key, nested in item.items():
                    key_text = str(key)
                    if AccountService._is_sensitive_key(key_text):
                        continue
                    cleaned[key_text] = sanitize(nested)
                return cleaned
            if isinstance(item, list):
                return [sanitize(nested) for nested in item]
            return item

        return sanitize(value)

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        normalized = key.lower().replace("-", "_")
        return normalized in SENSITIVE_DETAIL_KEYS or any(
            marker in normalized
            for marker in (
                "auth",
                "cookie",
                "credential",
                "password",
                "secret",
                "session",
                "token",
            )
        )

    @staticmethod
    def _ensure_platform(platform_id: str) -> None:
        if platform_id not in PLATFORM_IDS:
            raise ApiError(
                "VALIDATION_ERROR",
                f"Unsupported platform: {platform_id}",
                status_code=400,
                details={"supported": list(PLATFORM_IDS)},
            )

    @staticmethod
    def _account_row(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise ApiError("NOT_FOUND", "Crawler account not found", status_code=404)
        account = {
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "platformId": row["platform_id"],
            "accountId": row["account_id"],
            "username": row["username"],
            "displayName": row["display_name"],
            "avatarUrl": row["avatar_url"],
            "profileUrl": row["profile_url"],
            "status": row["status"],
            "loginType": row["login_type"],
            "lastLoginAt": row["last_login_at"],
            "lastCheckedAt": row["last_checked_at"],
            "details": loads(row["details_json"], {}),
            "error": loads(row["error_json"], None),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        return {key: value for key, value in account.items() if value is not None}
