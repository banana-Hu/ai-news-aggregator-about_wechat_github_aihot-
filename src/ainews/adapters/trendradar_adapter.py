"""
TrendRadar 适配器：将我们的数据源接入 TrendRadar 管道。

工作原理：
1. 运行我们的连接器（公众号/Telegram 等）
2. 将结果转换为 TrendRadar 的 txt 格式
3. TrendRadar 自动识别并处理（关键词过滤 + 权重排序 + 推送）

TrendRadar txt 格式：
  platform_id | platform_name
  1. 标题 [URL:xxx] [MOBILE:xxx]
  2. 标题 [URL:xxx] [MOBILE:xxx]
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ainews.schemas.normalized_item import NormalizedItem
from ainews.connectors.wechat_mp_connector import WeChatMpConnector
from ainews.connectors.aihot_connector import AIHOTConnector
from ainews.services.dedup_service import DedupService
from ainews.services.scoring_service import ScoringService

logger = logging.getLogger("ainews.trendradar_adapter")

# TrendRadar 输出目录
from ainews.core import PROJECT_ROOT
TRENDRADAR_OUTPUT = PROJECT_ROOT / "TrendRadar" / "output"


def items_to_trendradar_txt(
    items: list[NormalizedItem],
    output_dir: Path = None,
    platform_name: str = "微信公众号",
    platform_id: str = "wechat_mp",
) -> str:
    """将 NormalizedItem 列表转换为 TrendRadar txt 格式。"""
    if output_dir is None:
        now = datetime.now()
        date_folder = now.strftime("%Y年%m月%d日")
        time_str = now.strftime("%H时%M分")
        output_dir = TRENDRADAR_OUTPUT / date_folder / "txt"
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"{time_str}_wechat.txt"
    else:
        file_path = Path(output_dir) / f"wechat_mp_items.txt"

    lines = [f"{platform_id} | {platform_name}"]

    for i, item in enumerate(items, 1):
        title = item.title or "(无标题)"
        url = item.url or ""
        line = f"{i}. {title}"
        if url:
            line += f" [URL:{url}]"
        lines.append(line)

    content = "\n".join(lines) + "\n\n"
    file_path.write_text(content, encoding="utf-8")
    logger.info(f"写入 TrendRadar 格式: {file_path} ({len(items)} 条)")
    return str(file_path)


def run_wechat_mp_for_trendradar(
    max_articles: int = 20,
    output_dir: Path = None,
) -> list[NormalizedItem]:
    """运行公众号抓取，返回 NormalizedItem 列表。"""
    logger.info("适配器: 开始抓取公众号文章...")
    connector = WeChatMpConnector({
        "extract_content": False,
        "max_articles": max_articles,
    })
    items = connector.safe_fetch()

    if items:
        items = DedupService().deduplicate(items)
        items = ScoringService.score_all(items)
        items_to_trendradar_txt(items, output_dir=output_dir)

    logger.info(f"适配器: 公众号抓取完成 ({len(items)} 条)")
    return items


def run_aihot_for_trendradar(
    max_items: int = 30,
    output_dir: Path = None,
) -> list[NormalizedItem]:
    """运行 AIHOT 抓取，输出 TrendRadar 格式。"""
    logger.info("适配器: 开始抓取 AIHOT...")
    connector = AIHOTConnector({"max_items": max_items})
    items = connector.safe_fetch()

    if items:
        items = DedupService().deduplicate(items)
        items = ScoringService.score_all(items)
        items_to_trendradar_txt(
            items, output_dir=output_dir,
            platform_name="AIHOT 资讯", platform_id="aihot",
        )

    logger.info(f"适配器: AIHOT 抓取完成 ({len(items)} 条)")
    return items


def run_all_for_trendradar():
    """运行所有数据源，输出 TrendRadar 格式。"""
    now = datetime.now()
    date_folder = now.strftime("%Y年%m月%d日")
    time_str = now.strftime("%H时%M分")
    output_dir = TRENDRADAR_OUTPUT / date_folder / "txt"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_items = []
    all_items.extend(run_wechat_mp_for_trendradar(output_dir=output_dir))
    all_items.extend(run_aihot_for_trendradar(output_dir=output_dir))

    logger.info(f"适配器: 共输出 {len(all_items)} 条到 TrendRadar 目录")
    return all_items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_for_trendradar()
