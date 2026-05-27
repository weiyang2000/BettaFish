"""Pre-persistence identity blocklist filtering for MediaCrawler stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


BLOCK_RULES_ENV = "BETTAFISH_BLOCK_RULES_JSON"
BLOCK_STATS_ENV = "BETTAFISH_BLOCK_STATS_PATH"

GLOBAL_STABLE_ID_FIELDS = (
    "user_id",
    "sec_uid",
    "short_user_id",
    "user_unique_id",
    "user_url_token",
    "url_token",
    "author_id",
    "authorId",
    "author_uid",
    "authorUid",
    "author_mid",
    "mid",
    "uid",
)
PLATFORM_STABLE_ID_FIELDS = {
    "bili": ("user_id", "mid"),
    "dy": ("user_id", "sec_uid", "short_user_id", "user_unique_id"),
    "ks": ("user_id", "author_id", "authorId"),
    "tieba": ("user_link", "user_id"),
    "wb": ("user_id",),
    "xhs": ("user_id",),
    "zhihu": ("user_id", "user_url_token", "url_token", "user_link"),
}

# Tieba note/comment payloads in this MediaCrawler checkout expose user_link but
# may lack a numeric author ID. Nickname matching is limited to that platform as
# a fallback and only after the stable fields above are checked.
NICKNAME_FALLBACK_FIELDS = {
    "tieba": ("user_nickname",),
}


def normalize_block_rules(
    rules_by_platform: dict[str, list[dict[str, Any]] | list[str]] | None,
) -> dict[str, set[str]]:
    normalized: dict[str, set[str]] = {}
    for platform, rules in (rules_by_platform or {}).items():
        platform_rules: set[str] = set()
        for rule in rules:
            if isinstance(rule, dict):
                if rule.get("listType", "block") != "block":
                    continue
                raw_value = rule.get("userId")
            else:
                raw_value = rule
            value = normalize_identity_value(raw_value)
            if value:
                platform_rules.add(value)
        normalized[platform] = platform_rules
    return normalized


def normalize_identity_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "://" not in text:
        return text

    parsed = urlsplit(text)
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def record_identity_values(platform: str, record: dict[str, Any]) -> set[str]:
    fields = (
        *GLOBAL_STABLE_ID_FIELDS,
        *PLATFORM_STABLE_ID_FIELDS.get(platform, ()),
    )
    values = {
        normalized
        for field in fields
        if (normalized := normalize_identity_value(record.get(field)))
    }
    if values:
        return values

    return {
        normalized
        for field in NICKNAME_FALLBACK_FIELDS.get(platform, ())
        if (normalized := normalize_identity_value(record.get(field)))
    }


def should_block_record(
    platform: str,
    record: dict[str, Any],
    rules_by_platform: dict[str, set[str]],
) -> bool:
    blocked_ids = rules_by_platform.get(platform, set())
    if not blocked_ids:
        return False
    return bool(record_identity_values(platform, record) & blocked_ids)


def filter_records(
    platform: str,
    records: list[dict[str, Any]],
    rules_by_platform: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], int]:
    kept = [
        record
        for record in records
        if not should_block_record(platform, record, rules_by_platform)
    ]
    return kept, len(records) - len(kept)


def increment_filter_stats(
    stats_path: str | None,
    platform: str,
    item_type: str,
) -> None:
    if not stats_path:
        return

    path = Path(stats_path)
    stats = _read_stats(path)
    platform_summary = stats.setdefault("platform_summary", {})
    counters = platform_summary.setdefault(
        platform,
        {"filtered_notes": 0, "filtered_comments": 0},
    )
    key = "filtered_comments" if item_type == "comment" else "filtered_notes"
    counters[key] = counters.get(key, 0) + 1
    stats[key] = stats.get(key, 0) + 1
    path.write_text(json.dumps(stats, ensure_ascii=False), encoding="utf-8")


def _read_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"platform_summary": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return {"platform_summary": {}}


class BlocklistStoreProxy:
    """Proxy MediaCrawler store writes and drop blocked records before save."""

    def __init__(
        self,
        delegate: Any,
        platform: str,
        rules_by_platform: dict[str, set[str]],
        stats_path: str | None = None,
        logger: Any | None = None,
    ):
        self._delegate = delegate
        self._platform = platform
        self._rules_by_platform = rules_by_platform
        self._stats_path = stats_path
        self._logger = logger

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    async def store_content(self, *args: Any, **kwargs: Any) -> Any:
        item = _payload_from_call(args, kwargs, ("content_item", "item"))
        if self._should_drop(item, "content"):
            return None
        return await self._delegate.store_content(*args, **kwargs)

    async def store_comment(self, *args: Any, **kwargs: Any) -> Any:
        item = _payload_from_call(args, kwargs, ("comment_item", "item"))
        if self._should_drop(item, "comment"):
            return None
        return await self._delegate.store_comment(*args, **kwargs)

    def _should_drop(self, item: Any, item_type: str) -> bool:
        if not isinstance(item, dict):
            return False
        if not should_block_record(self._platform, item, self._rules_by_platform):
            return False

        increment_filter_stats(self._stats_path, self._platform, item_type)
        if self._logger:
            self._logger.info(
                f"[bettafish.identity_filter] skipped {self._platform} "
                f"{item_type} before persistence"
            )
        return True


def _payload_from_call(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    names: tuple[str, ...],
) -> Any:
    for name in names:
        if name in kwargs:
            return kwargs[name]
    return args[0] if args else None
