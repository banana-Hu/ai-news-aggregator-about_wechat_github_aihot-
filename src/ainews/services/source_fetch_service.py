"""
统一外部数据源抓取入口。

提供 fetch_external_ai_sources() 函数：
1. 并行或串行调用所有注册的 Connector
2. 合并结果
3. 去重
4. 评分
5. 排序输出
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import yaml

from ainews.connectors.github_connector import GitHubConnector
from ainews.connectors.aihot_connector import AIHOTConnector
from ainews.connectors.wechat_mp_connector import WeChatMpConnector
from ainews.services.dedup_service import DedupService
from ainews.services.scoring_service import ScoringService
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# 默认配置路径
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "sources.yaml")


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """加载配置文件。"""
    if not os.path.exists(config_path):
        logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
        return {}
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def fetch_external_ai_sources(
    config: Optional[dict] = None,
    config_path: str = DEFAULT_CONFIG_PATH,
    dedup: bool = True,
    scoring: bool = True,
    verbose: bool = False,
) -> list[NormalizedItem]:
    """统一外部 AI 信息源抓取入口。

    调用所有注册的 Connector，合并、去重、评分后返回。

    Args:
        config: 配置字典。如提供则覆盖文件配置。
        config_path: 配置文件路径。config 参数优先。
        dedup: 是否去重（默认 True）
        scoring: 是否评分（默认 True）
        verbose: 是否打印详细日志

    Returns:
        list[NormalizedItem]: 标准化、去重、评分后的数据条目列表。
    """
    if config is None:
        config = load_config(config_path)

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    start_time = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("开始外部 AI 信息源抓取")
    logger.info(f"配置: {json.dumps(config, ensure_ascii=False, default=str)[:200]}")

    # 1. 初始化 Connectors
    github_cfg = config.get("github", {})
    aihot_cfg = config.get("aihot", {})
    wechat_mp_cfg = config.get("wechat_mp", {})

    connectors = [
        ("GitHub", GitHubConnector(github_cfg)),
        ("AIHOT", AIHOTConnector(aihot_cfg)),
    ]
    # 公众号连接器（仅在启用或配置了账号时加入）
    if wechat_mp_cfg.get("enabled", True) or wechat_mp_cfg.get("accounts"):
        connectors.append(("WeChatMP", WeChatMpConnector(wechat_mp_cfg)))

    # 2. 串行抓取（避免限流 + 隔离故障）
    all_items: list[NormalizedItem] = []
    errors = []

    for name, connector in connectors:
        try:
            logger.info(f"[{name}] 开始抓取...")
            items = connector.safe_fetch()
            logger.info(f"[{name}] 抓取到 {len(items)} 条")
            all_items.extend(items)
        except Exception as e:
            logger.error(f"[{name}] 连接器异常: {e}")
            errors.append({"source": name, "error": str(e)})

    logger.info(f"合并后共 {len(all_items)} 条（原始）")

    # 3. 去重
    dedup_stats = {"url_dup": 0, "title_dup": 0, "content_dup": 0, "kept": 0}
    if dedup and all_items:
        dedup_service = DedupService()
        all_items = dedup_service.deduplicate(all_items)
        dedup_stats = dedup_service.get_stats()
        logger.info(f"去重后剩余 {len(all_items)} 条")

    # 4. 评分
    if scoring and all_items:
        all_items = ScoringService.score_all(all_items)

    # 5. 报告
    elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
    total_raw = len(all_items) + dedup_stats["url_dup"] + dedup_stats["title_dup"] + dedup_stats["content_dup"]
    report = {
        "total_raw": total_raw,
        "total_deduped": len(all_items),
        "github_count": sum(1 for i in all_items if i.source == "github"),
        "aihot_count": sum(1 for i in all_items if i.source == "aihot"),
        "wechat_mp_count": sum(1 for i in all_items if i.source == "wechat_mp"),
        "errors": errors,
        "elapsed_seconds": round(elapsed, 2),
    }

    logger.info(f"抓取完成: {json.dumps(report, ensure_ascii=False)}")
    logger.info("=" * 60)

    return all_items


def fetch_and_save(
    output_path: str = "ai_news_output.json",
    **kwargs,
):
    """抓取并保存到 JSON 文件。"""
    items = fetch_external_ai_sources(**kwargs)
    data = [item.to_dict() for item in items]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"已保存 {len(data)} 条到 {output_path}")
    return items
