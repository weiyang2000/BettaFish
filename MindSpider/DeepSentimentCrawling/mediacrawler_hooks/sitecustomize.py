"""Install BettaFish MediaCrawler store hooks when the adapter enables them."""

from __future__ import annotations

import importlib
import json
import os
from typing import Any

from identity_filter import (
    BLOCK_RULES_ENV,
    BLOCK_STATS_ENV,
    BlocklistStoreProxy,
    normalize_block_rules,
)


STORE_FACTORIES = (
    ("store.bilibili", "BiliStoreFactory", "bili"),
    ("store.douyin", "DouyinStoreFactory", "dy"),
    ("store.kuaishou", "KuaishouStoreFactory", "ks"),
    ("store.tieba", "TieBaStoreFactory", "tieba"),
    ("store.weibo", "WeibostoreFactory", "wb"),
    ("store.xhs", "XhsStoreFactory", "xhs"),
    ("store.zhihu", "ZhihuStoreFactory", "zhihu"),
)


def _load_rules_from_env() -> dict[str, set[str]]:
    raw_rules = os.getenv(BLOCK_RULES_ENV)
    if not raw_rules:
        return {}
    try:
        return normalize_block_rules(json.loads(raw_rules))
    except json.JSONDecodeError:
        return {}


def _logger() -> Any | None:
    try:
        from tools import utils

        return utils.logger
    except Exception:
        return None


def _patch_factory(
    module_name: str,
    factory_name: str,
    platform: str,
    rules_by_platform: dict[str, set[str]],
    stats_path: str | None,
) -> None:
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name)
    original_create_store = factory.create_store
    if getattr(original_create_store, "_bettafish_blocklist_wrapped", False):
        return

    def create_store() -> Any:
        delegate = original_create_store()
        return BlocklistStoreProxy(
            delegate,
            platform,
            rules_by_platform,
            stats_path=stats_path,
            logger=_logger(),
        )

    create_store._bettafish_blocklist_wrapped = True
    factory.create_store = staticmethod(create_store)


def _install() -> None:
    rules_by_platform = _load_rules_from_env()
    if not any(rules_by_platform.values()):
        return

    stats_path = os.getenv(BLOCK_STATS_ENV)
    for module_name, factory_name, platform in STORE_FACTORIES:
        try:
            _patch_factory(
                module_name,
                factory_name,
                platform,
                rules_by_platform,
                stats_path,
            )
        except Exception as exc:
            logger = _logger()
            if logger:
                logger.warning(
                    f"[bettafish.identity_filter] could not patch {module_name}: {exc}"
                )


_install()
