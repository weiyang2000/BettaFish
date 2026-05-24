"""Platform policy and identity-list persistence."""

from __future__ import annotations

import sqlite3
from typing import Any

from apps.api.schemas import ApiError, IdentityRuleInput, PLATFORM_IDS, PlatformPolicyInput
from apps.api.services.accounts import AccountService
from apps.api.services.common import new_id, utc_now
from apps.api.storage import Store, dumps, loads


PLATFORM_NAMES = {
    "xhs": "小红书",
    "dy": "抖音",
    "ks": "快手",
    "bili": "哔哩哔哩",
    "wb": "微博",
    "tieba": "百度贴吧",
    "zhihu": "知乎",
}


def default_policy(platform_id: str, updated_at: str | None = None) -> dict[str, Any]:
    policy = PlatformPolicyInput(
        enabled=True,
        crawlDepth=3,
        maxKeywords=100,
        maxNotesPerKeyword=50,
        maxCommentsPerNote=100,
        keywords=[],
        keywordSource="manual",
    ).to_policy(platform_id, updated_at or utc_now())
    return policy


class PlatformService:
    def __init__(self, store: Store, account_service: AccountService | None = None):
        self.store = store
        self.account_service = account_service

    def ensure_platform(self, platform_id: str) -> None:
        if platform_id not in PLATFORM_IDS:
            raise ApiError(
                "VALIDATION_ERROR",
                f"Unsupported platform: {platform_id}",
                status_code=400,
                details={"supported": list(PLATFORM_IDS)},
            )

    def list_platforms(self, workspace_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": platform_id,
                "name": PLATFORM_NAMES[platform_id],
                "enabled": self.get_policy(workspace_id, platform_id)["enabled"],
                "crawlerType": "search",
                "policy": self.get_policy(workspace_id, platform_id),
                "identityRuleCounts": self.identity_counts(workspace_id, platform_id),
                "accountCounts": self.account_counts(workspace_id, platform_id),
            }
            for platform_id in PLATFORM_IDS
        ]

    def account_counts(self, workspace_id: str, platform_id: str) -> dict[str, int]:
        if not self.account_service:
            return {
                "active": 0,
                "loginRequired": 0,
                "expired": 0,
                "disabled": 0,
                "error": 0,
                "unknown": 0,
            }
        return self.account_service.account_counts(workspace_id, platform_id)

    def get_policy(self, workspace_id: str, platform_id: str) -> dict[str, Any]:
        self.ensure_platform(platform_id)
        row = self.store.query_one(
            "SELECT * FROM crawler_platform_configs WHERE workspace_id = ? AND platform_id = ?",
            (workspace_id, platform_id),
        )
        if not row:
            return default_policy(platform_id)
        return {
            "platformId": row["platform_id"],
            "enabled": bool(row["enabled"]),
            "crawlDepth": row["crawl_depth"],
            "maxKeywords": row["max_keywords"],
            "maxNotesPerKeyword": row["max_notes_per_keyword"],
            "maxCommentsPerNote": row["max_comments_per_note"],
            "keywords": loads(row["keywords_json"], []),
            "keywordSource": row["keyword_source"],
            "frequency": loads(row["frequency_json"], {"mode": "manual", "timezone": "Asia/Shanghai"}),
            "loginType": row["login_type"],
            "headless": bool(row["headless"]),
            "updatedAt": row["updated_at"],
            **self._optional_user("updatedBy", row["updated_by_json"]),
        }

    def update_policy(
        self,
        workspace_id: str,
        platform_id: str,
        policy: PlatformPolicyInput,
    ) -> dict[str, Any]:
        self.ensure_platform(platform_id)
        updated_at = utc_now()
        self.store.execute(
            """
            INSERT INTO crawler_platform_configs (
                workspace_id, platform_id, enabled, crawl_depth, max_keywords,
                max_notes_per_keyword, max_comments_per_note, keywords_json,
                keyword_source, frequency_json, login_type, headless, updated_at,
                updated_by_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace_id, platform_id) DO UPDATE SET
                enabled = excluded.enabled,
                crawl_depth = excluded.crawl_depth,
                max_keywords = excluded.max_keywords,
                max_notes_per_keyword = excluded.max_notes_per_keyword,
                max_comments_per_note = excluded.max_comments_per_note,
                keywords_json = excluded.keywords_json,
                keyword_source = excluded.keyword_source,
                frequency_json = excluded.frequency_json,
                login_type = excluded.login_type,
                headless = excluded.headless,
                updated_at = excluded.updated_at,
                updated_by_json = excluded.updated_by_json
            """,
            (
                workspace_id,
                platform_id,
                1 if policy.enabled else 0,
                policy.crawlDepth,
                policy.maxKeywords,
                policy.maxNotesPerKeyword,
                policy.maxCommentsPerNote,
                dumps(policy.keywords),
                policy.keywordSource,
                dumps(policy.frequency.model_dump(mode="json")),
                policy.loginType,
                1 if policy.headless else 0,
                updated_at,
                None,
            ),
        )
        return self.get_policy(workspace_id, platform_id)

    def identity_counts(self, workspace_id: str, platform_id: str) -> dict[str, int]:
        rows = self.store.query_all(
            """
            SELECT list_type, COUNT(*) AS count
            FROM crawler_identity_rules
            WHERE workspace_id = ? AND platform_id = ?
            GROUP BY list_type
            """,
            (workspace_id, platform_id),
        )
        counts = {"allow": 0, "block": 0}
        for row in rows:
            counts[row["list_type"]] = row["count"]
        return counts

    def list_identity_rules(
        self,
        workspace_id: str,
        platform_id: str,
        list_type: str | None,
    ) -> list[dict[str, Any]]:
        self.ensure_platform(platform_id)
        if list_type and list_type not in {"allow", "block"}:
            raise ApiError("VALIDATION_ERROR", "listType must be allow or block", status_code=400)
        params: list[Any] = [workspace_id, platform_id]
        where = "workspace_id = ? AND platform_id = ?"
        if list_type:
            where += " AND list_type = ?"
            params.append(list_type)
        rows = self.store.query_all(
            f"""
            SELECT *
            FROM crawler_identity_rules
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        )
        return [self._identity_row(row) for row in rows]

    def create_identity_rule(
        self,
        workspace_id: str,
        platform_id: str,
        payload: IdentityRuleInput,
    ) -> dict[str, Any]:
        self.ensure_platform(platform_id)
        opposite = "block" if payload.listType == "allow" else "allow"
        existing_opposite = self.store.query_one(
            """
            SELECT id FROM crawler_identity_rules
            WHERE workspace_id = ? AND platform_id = ? AND list_type = ? AND user_id = ?
            """,
            (workspace_id, platform_id, opposite, payload.userId),
        )
        if existing_opposite:
            raise ApiError(
                "CONFLICT",
                "User ID already exists in the opposite identity list",
                status_code=409,
                details={"userId": payload.userId, "oppositeListType": opposite},
            )

        rule_id = new_id("identity")
        created_at = utc_now()
        try:
            self.store.execute(
                """
                INSERT INTO crawler_identity_rules (
                    id, workspace_id, platform_id, list_type, user_id, label,
                    reason, expires_at, created_at, created_by_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    workspace_id,
                    platform_id,
                    payload.listType,
                    payload.userId,
                    payload.label,
                    payload.reason,
                    payload.expiresAt,
                    created_at,
                    dumps(payload.createdBy.model_dump(exclude_none=True))
                    if payload.createdBy
                    else None,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ApiError(
                "CONFLICT",
                "User ID already exists in this identity list",
                status_code=409,
                details={"userId": payload.userId, "listType": payload.listType},
            ) from exc

        row = self.store.query_one(
            "SELECT * FROM crawler_identity_rules WHERE id = ?",
            (rule_id,),
        )
        return self._identity_row(row)

    def delete_identity_rule(
        self,
        workspace_id: str,
        platform_id: str,
        rule_id: str,
    ) -> None:
        self.ensure_platform(platform_id)
        existing = self.store.query_one(
            """
            SELECT id FROM crawler_identity_rules
            WHERE workspace_id = ? AND platform_id = ? AND id = ?
            """,
            (workspace_id, platform_id, rule_id),
        )
        if not existing:
            raise ApiError("NOT_FOUND", "Identity rule not found", status_code=404)
        self.store.execute(
            "DELETE FROM crawler_identity_rules WHERE workspace_id = ? AND platform_id = ? AND id = ?",
            (workspace_id, platform_id, rule_id),
        )

    @staticmethod
    def _identity_row(row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            raise ApiError("NOT_FOUND", "Identity rule not found", status_code=404)
        return {
            "id": row["id"],
            "platformId": row["platform_id"],
            "listType": row["list_type"],
            "userId": row["user_id"],
            "label": row["label"],
            "reason": row["reason"],
            "expiresAt": row["expires_at"],
            "createdAt": row["created_at"],
            **PlatformService._optional_user("createdBy", row["created_by_json"]),
        }

    @staticmethod
    def _optional_user(key: str, value: str | None) -> dict[str, Any]:
        user = loads(value, None)
        return {key: user} if user else {}
