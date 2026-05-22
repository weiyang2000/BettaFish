"""System configuration API with masked secret reads."""

from __future__ import annotations

from typing import Any

from apps.api.schemas import MASK, UserRef
from apps.api.services.common import utc_now
from apps.api.storage import Store, dumps, loads


CONFIG_KEYS = [
    "HOST",
    "PORT",
    "DB_DIALECT",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "DB_CHARSET",
    "INSIGHT_ENGINE_API_KEY",
    "INSIGHT_ENGINE_BASE_URL",
    "INSIGHT_ENGINE_MODEL_NAME",
    "MEDIA_ENGINE_API_KEY",
    "MEDIA_ENGINE_BASE_URL",
    "MEDIA_ENGINE_MODEL_NAME",
    "QUERY_ENGINE_API_KEY",
    "QUERY_ENGINE_BASE_URL",
    "QUERY_ENGINE_MODEL_NAME",
    "REPORT_ENGINE_API_KEY",
    "REPORT_ENGINE_BASE_URL",
    "REPORT_ENGINE_MODEL_NAME",
    "MINDSPIDER_API_KEY",
    "MINDSPIDER_BASE_URL",
    "MINDSPIDER_MODEL_NAME",
    "FORUM_HOST_API_KEY",
    "FORUM_HOST_BASE_URL",
    "FORUM_HOST_MODEL_NAME",
    "KEYWORD_OPTIMIZER_API_KEY",
    "KEYWORD_OPTIMIZER_BASE_URL",
    "KEYWORD_OPTIMIZER_MODEL_NAME",
    "TAVILY_API_KEY",
    "SEARCH_TOOL_TYPE",
    "BOCHA_BASE_URL",
    "BOCHA_WEB_SEARCH_API_KEY",
    "ANSPIRE_BASE_URL",
    "ANSPIRE_API_KEY",
]

SEARCH_TOOL_OPTIONS = ["AnspireAPI", "BochaAPI"]


def is_sensitive_key(key: str) -> bool:
    return key.upper().endswith(("API_KEY", "PASSWORD", "SECRET", "TOKEN"))


def config_group(key: str) -> str:
    if key.startswith(("HOST", "PORT")):
        return "server"
    if key.startswith("DB_"):
        return "database"
    if "SEARCH" in key or key.startswith(("TAVILY", "BOCHA", "ANSPIRE")):
        return "search"
    if key.startswith("MINDSPIDER"):
        return "crawler"
    return "llm"


def config_type(key: str, value: Any) -> str:
    if is_sensitive_key(key):
        return "secret"
    if key == "SEARCH_TOOL_TYPE":
        return "enum"
    if key.endswith("_URL") or key.endswith("BASE_URL"):
        return "url"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


class ConfigurationService:
    def __init__(self, store: Store):
        self.store = store

    def list_fields(self, workspace_id: str) -> list[dict[str, Any]]:
        persisted = {
            row["key"]: row
            for row in self.store.query_all(
                "SELECT * FROM app_configs WHERE workspace_id = ?",
                (workspace_id,),
            )
        }
        settings_values = self._settings_values()
        fields = []
        for key in CONFIG_KEYS:
            persisted_row = persisted.get(key)
            if persisted_row:
                raw_value = loads(persisted_row["value_json"], None)
                updated_at = persisted_row["updated_at"]
            else:
                raw_value = settings_values.get(key, "")
                updated_at = None

            sensitive = is_sensitive_key(key)
            display_value = MASK if sensitive and raw_value not in (None, "") else self._to_string(raw_value)
            field = {
                "key": key,
                "label": key.replace("_", " ").title(),
                "group": config_group(key),
                "type": config_type(key, raw_value),
                "value": display_value,
                "editable": True,
                "sensitive": sensitive,
                "required": key in {"DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"},
            }
            if key == "SEARCH_TOOL_TYPE":
                field["options"] = SEARCH_TOOL_OPTIONS
            if updated_at:
                field["lastUpdatedAt"] = updated_at
            fields.append(field)
        return fields

    def update_fields(
        self,
        workspace_id: str,
        values: dict[str, str | int | float | bool | None],
        updated_by: UserRef | None,
    ) -> None:
        updated_at = utc_now()
        updated_by_json = (
            dumps(updated_by.model_dump(exclude_none=True)) if updated_by else None
        )
        for key, value in values.items():
            if key not in CONFIG_KEYS:
                continue
            sensitive = is_sensitive_key(key)
            if sensitive and value in (None, "", MASK):
                continue
            self.store.execute(
                """
                INSERT INTO app_configs (
                    workspace_id, key, value_json, sensitive, updated_at, updated_by_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(workspace_id, key) DO UPDATE SET
                    value_json = excluded.value_json,
                    sensitive = excluded.sensitive,
                    updated_at = excluded.updated_at,
                    updated_by_json = excluded.updated_by_json
                """,
                (
                    workspace_id,
                    key,
                    dumps(value),
                    1 if sensitive else 0,
                    updated_at,
                    updated_by_json,
                ),
            )

    def _settings_values(self) -> dict[str, Any]:
        try:
            from config import reload_settings, settings

            reload_settings()
            return {key: getattr(settings, key, "") for key in CONFIG_KEYS}
        except Exception:
            return {key: "" for key in CONFIG_KEYS}

    @staticmethod
    def _to_string(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

