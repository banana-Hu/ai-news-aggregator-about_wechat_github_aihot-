"""
统一外部数据源抓取入口。

提供：
- fetch_external_ai_sources() — 原始统一入口
- fetch_sources() — 按数据源名称列表抓取，供 UI 层调用
- fetch_and_push() — 抓取 + 推送，供 UI 层调用
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import yaml

from ainews.core import CONFIG_PATH, read_lark_chat_id
from ainews.connectors import get_all_connectors, CONNECTORS
from ainews.services.dedup_service import DedupService
from ainews.services.scoring_service import ScoringService
from ainews.services.push_service import push_ai_daily
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)


def load_config(config_path: str = "") -> dict:
    """加载配置文件。"""
    if not config_path:
        config_path = str(CONFIG_PATH)
    if not config_path or not __import__("os").path.exists(config_path):
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ============================================================
# 统一抓取接口（UI 层调用）
# ============================================================


def fetch_sources(
    sources: list[str] | None = None,
    config: dict | None = None,
    dedup: bool = True,
    scoring: bool = True,
    verbose: bool = False,
    log_func=None,
) -> list[NormalizedItem]:
    """按数据源名称列表抓取，返回去重评分后的结果。

    Args:
        sources: 数据源列表，如 ["aihot", "wechat_mp"]，None=默认列表
        config: 配置字典
        dedup: 是否去重
        scoring: 是否评分
        verbose: 详细日志
        log_func: UI 日志回调 (msg, kind)

    Returns:
        list[NormalizedItem]
    """
    if config is None:
        config = load_config()

    def _log(msg, kind="info"):
        logger.info(f"[{kind}] {msg}")
        if log_func:
            log_func(msg, kind)

    if sources is None:
        sources = ["aihot", "wechat_mp"]

    _log(f"开始抓取: {', '.join(sources)}")

    all_items = []
    connectors = get_all_connectors(config, sources)

    for name, connector in connectors:
        try:
            _log(f"正在获取 {name} 数据...", "info")
            items = connector.safe_fetch()
            _log(f"{name}: {len(items)} 条", "ok" if items else "warn")
            all_items.extend(items)
        except Exception as e:
            _log(f"{name} 异常: {e}", "err")

    if dedup and all_items:
        svc = DedupService()
        all_items = svc.deduplicate(all_items)
        _log(f"去重后: {len(all_items)} 条", "info")

    if scoring and all_items:
        all_items = ScoringService.score_all(all_items)
        _log(f"评分完成", "info")

    # 自动发现创作者
    try:
        from ainews.services.subscription_service import auto_discover
        stats = auto_discover(all_items)
        if stats["new"] or stats["auto_followed"]:
            _log(f"创作者: 新增{stats['new']}, 更新{stats['updated']}, 自动关注{stats['auto_followed']}", "info")
    except Exception as e:
        logger.debug(f"创作者发现跳过: {e}")

    return all_items


def fetch_and_push(
    sources: list[str] | None = None,
    chat_id: str | None = None,
    config: dict | None = None,
    log_func=None,
) -> bool:
    """抓取并推送飞书。

    Args:
        sources: 数据源列表
        chat_id: 飞书群 ID，None 从配置读取
        config: 配置字典
        log_func: UI 日志回调

    Returns:
        是否成功
    """
    def _log(msg, kind="info"):
        logger.info(f"[{kind}] {msg}")
        if log_func:
            log_func(msg, kind)

    items = fetch_sources(sources=sources, config=config, log_func=log_func)

    if not items:
        _log("无数据可推送", "warn")
        return False

    cid = chat_id or read_lark_chat_id()
    if not cid:
        _log("未配置飞书群 ID", "warn")
        return False

    _log(f"推送 {len(items)} 条到飞书...", "info")
    ok = push_ai_daily(items, chat_id=cid, chat_name=None)
    _log("推送成功 ✅" if ok else "推送失败 ❌", "ok" if ok else "err")
    return ok


# ============================================================
# 原有入口（兼容）
# ============================================================


def fetch_external_ai_sources(
    config: Optional[dict] = None,
    config_path: str = "",
    dedup: bool = True,
    scoring: bool = True,
    verbose: bool = False,
) -> list[NormalizedItem]:
    """原有统一入口，保持向下兼容。"""
    if config is None:
        config = load_config(config_path)

    sources = ["aihot", "wechat_mp"]
    if config.get("github", {}).get("queries"):
        sources.append("github")

    return fetch_sources(sources=sources, config=config, dedup=dedup, scoring=scoring, verbose=verbose)


def fetch_and_save(output_path: str = "ai_news_output.json", **kwargs):
    """抓取并保存到 JSON 文件。"""
    items = fetch_external_ai_sources(**kwargs)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump([i.to_dict() for i in items], f, ensure_ascii=False, indent=2)
    logger.info(f"已保存 {len(items)} 条到 {output_path}")
    return items
