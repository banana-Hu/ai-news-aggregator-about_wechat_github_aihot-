"""
基础评分服务。
对 NormalizedItem 进行规则评分，不使用大模型。
"""

import logging
from datetime import datetime, timezone, timedelta

from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)


class ScoringService:
    """基础评分服务。"""

    @staticmethod
    def score(item: NormalizedItem) -> int:
        """对单条数据进行评分。

        GitHub 项目评分规则：
        - Star > 10000：+20
        - Star > 1000：+10
        - 最近 7 天更新：+10
        - 有 README：+10
        - 标题或简介包含 Agent / MCP / RAG / LLM：+10
        - 有 Release：+5

        AIHOT 内容评分规则：
        - 来源为精选/日报：+15
        - 标题包含 OpenAI / Claude / Gemini / Agent / MCP / 国产大模型：+10
        - 发布时间为当天：+10
        - 内容长度过短：-5
        """
        score = 0

        if item.source == "github":
            score = ScoringService._score_github(item)
        elif item.source == "aihot":
            score = ScoringService._score_aihot(item)

        # 保底分数
        score = max(0, min(100, score))

        # 更新到 item
        item.score = score
        return score

    @staticmethod
    def _score_github(item: NormalizedItem) -> int:
        score = 0
        raw = item.raw or {}

        # Star 评分
        stars = raw.get("stars", 0) or 0
        if stars > 10000:
            score += 20
        elif stars > 1000:
            score += 10

        # 最近更新
        updated_at = raw.get("updated_at") or raw.get("pushed_at")
        if updated_at:
            try:
                updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - updated < timedelta(days=7):
                    score += 10
            except (ValueError, AttributeError):
                pass

        # 有 README
        if raw.get("has_readme"):
            score += 10

        # 关键词命中
        text = f"{item.title} {item.summary}".lower()
        keywords = ["agent", "mcp", "rag", "llm", "multi-agent", "autonomous"]
        for kw in keywords:
            if kw in text:
                score += 10
                break

        # 有 Release
        if raw.get("latest_release"):
            score += 5

        return score

    @staticmethod
    def _score_aihot(item: NormalizedItem) -> int:
        score = 0

        # 日报条目基础分高
        if item.source_type == "aihot_daily":
            score += 15

        # 标题关键词
        title = item.title.lower()
        hot_keywords = [
            "openai", "claude", "gemini", "gpt-5", "agent", "mcp",
            "国产大模型", "deepseek", "qwen", "doubao", "llama",
            "seed", "字节", "百度", "阿里", "腾讯", "华为",
        ]
        for kw in hot_keywords:
            if kw in title:
                score += 10
                break

        # 发布时间为当天
        if item.published_at:
            try:
                published = datetime.fromisoformat(
                    item.published_at.replace("Z", "+00:00")
                )
                if published.date() == datetime.now(timezone.utc).date():
                    score += 10
            except (ValueError, AttributeError):
                pass

        # 内容过短扣分
        total_len = len(item.title or "") + len(item.summary or "")
        if total_len < 30:
            score -= 5

        return score

    @staticmethod
    def score_all(items: list[NormalizedItem]) -> list[NormalizedItem]:
        """批量评分，同时返回按分数降序排列的结果。"""
        for item in items:
            ScoringService.score(item)

        items.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"评分完成: {len(items)} 条")
        return items
