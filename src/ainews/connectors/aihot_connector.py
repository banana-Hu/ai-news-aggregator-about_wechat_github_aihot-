"""
AIHOT (aihot.virxact.com) 数据源连接器。
通过公开 REST API 获取 AI 资讯、日报等内容。
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from .base import BaseConnector
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# API 基础 URL
BASE_URL = "https://aihot.virxact.com"

# 默认 UA（必须携带，否则 403）
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 aihot-skill/0.2.0"
)

# 分类映射
CATEGORY_MAP = {
    "ai-models": "模型发布/更新",
    "ai-products": "产品发布/更新",
    "industry": "行业动态",
    "paper": "论文研究",
    "tip": "技巧与观点",
}

# 反向分类标签
CATEGORY_TAGS = {
    "ai-models": ["模型", "发布", "大模型"],
    "ai-products": ["产品", "工具"],
    "industry": ["行业", "动态"],
    "paper": ["论文", "研究"],
    "tip": ["技巧", "观点"],
}


class AIHOTConnector(BaseConnector):
    """AIHOT (aihot.virxact.com) 数据源连接器。"""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.base_url = config.get("base_url", BASE_URL)
        self.user_agent = config.get("user_agent") or os.environ.get(
            "AIHOT_USER_AGENT", DEFAULT_USER_AGENT
        )
        self.max_retries = config.get("max_retries", 3)
        self.request_timeout = config.get("request_timeout", 15)
        self.max_items = config.get("max_items", 50)
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        })
        return session

    def _request(self, path: str, params: Optional[dict] = None) -> Optional[dict]:
        """通用 API 请求封装。"""
        url = f"{self.base_url}{path}"
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(
                    url, params=params, timeout=self.request_timeout
                )
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    self.logger.warning(f"资源不存在: {url}")
                    return None
                elif resp.status_code == 429:
                    wait = 10 * (attempt + 1)
                    self.logger.warning(f"限流触发，等待 {wait}s 后重试")
                    self.rate_limit_sleep(wait)
                    continue
                elif resp.status_code == 403:
                    self.logger.error(f"访问被拒(403)，检查 UA 是否设置正确: {url}")
                    return None
                else:
                    self.logger.warning(
                        f"请求返回 {resp.status_code}: {url}, {resp.text[:200]}"
                    )
                    if attempt < self.max_retries - 1:
                        self.rate_limit_sleep(2 ** attempt)
            except requests.exceptions.Timeout:
                self.logger.warning(f"请求超时: {url}, attempt={attempt + 1}")
                if attempt < self.max_retries - 1:
                    self.rate_limit_sleep(2 ** attempt)
            except requests.exceptions.ConnectionError as e:
                self.logger.warning(f"连接错误: {url}, {e}")
                if attempt < self.max_retries - 1:
                    self.rate_limit_sleep(5)
            except Exception as e:
                self.logger.error(f"请求异常: {url}, {e}")
                return None
        return None

    def _fetch_items(
        self,
        mode: str = "selected",
        category: Optional[str] = None,
        since: Optional[str] = None,
        take: int = 50,
        q: Optional[str] = None,
    ) -> list[dict]:
        """从 /api/public/items 拉取动态。

        Args:
            mode: "selected" 或 "all"
            category: 分类筛选
            since: ISO 时间起点
            take: 条数 (1-100)
            q: 关键词搜索

        Returns:
            items 列表
        """
        params = {"mode": mode, "take": min(take, 100)}
        if category:
            params["category"] = category
        if since:
            params["since"] = since
        if q:
            params["q"] = q

        self.logger.info(f"拉取 AIHOT items: mode={mode}, category={category}, take={take}")
        data = self._request("/api/public/items", params)

        if not data:
            return []
        items = data.get("items", [])
        self.logger.info(f"获取到 {len(items)} 条")
        self.rate_limit_sleep(0.5)
        return items

    def _fetch_daily(self, date_str: Optional[str] = None) -> Optional[dict]:
        """拉取日报。

        Args:
            date_str: YYYY-MM-DD 格式，None 表示最新日报

        Returns:
            日报数据 dict
        """
        if date_str:
            path = f"/api/public/daily/{date_str}"
        else:
            path = "/api/public/daily"

        self.logger.info(f"拉取 AIHOT 日报: {path}")
        data = self._request(path)
        self.rate_limit_sleep(0.3)
        return data

    def _item_to_normalized(self, item: dict, source_type: str = "aihot_news") -> NormalizedItem:
        """将 API 返回的单条 item 转为 NormalizedItem。"""
        title = item.get("title", "")
        url = item.get("url", "")
        source = item.get("source", "AIHOT")
        published_at = item.get("publishedAt")
        summary = item.get("summary", "")
        score = item.get("score", 0)
        selected = item.get("selected", False)
        category = item.get("category")

        # 自动标签
        tags = self._auto_tag(title, summary, category)

        return NormalizedItem(
            source="aihot",
            source_type=source_type,
            title=title,
            url=url,
            author=source,
            published_at=published_at,
            summary=summary,
            tags=tags,
            score=score if score else 0,
            raw={
                "id": item.get("id"),
                "title_en": item.get("title_en"),
                "category": category,
                "selected": selected,
                "score": score,
            },
        )

    def _auto_tag(self, title: str, summary: str, category: Optional[str] = None) -> list[str]:
        """根据标题、摘要和分类自动打标签。"""
        tags = ["AI"]
        text = f"{title} {summary}".lower()

        # 分类映射标签
        if category and category in CATEGORY_TAGS:
            tags.extend(CATEGORY_TAGS[category])

        # 模型/公司关键词
        model_keywords = ["openai", "claude", "gemini", "gpt", "llama", "mistral",
                          "deepseek", "qwen", "doubao", "seed"]
        for kw in model_keywords:
            if kw in text:
                tags.append(kw.upper())

        # 主题关键词
        topic_keywords = {
            "Agent": ["agent", "智能体", "autonomous"],
            "MCP": ["mcp", "model context protocol"],
            "RAG": ["rag", "检索", "embedding", "vector"],
            "多模态": ["多模态", "multimodal", "video", "image", "audio"],
            "开源": ["开源", "open source", "开源模型"],
            "安全": ["安全", "security", "safety"],
        }
        for tag, keywords in topic_keywords.items():
            for kw in keywords:
                if kw in text:
                    tags.append(tag)
                    break

        # 去重
        seen = set()
        unique_tags = []
        for t in tags:
            if t not in seen:
                seen.add(t)
                unique_tags.append(t)
        return unique_tags

    def fetch(self, **kwargs) -> list[NormalizedItem]:
        """执行 AIHOT 数据抓取。

        策略：
        1. 优先拉取 items 精选数据 (mode=selected)
        2. 再拉取最新日报
        3. 合并去重将在 service 层处理

        Args:
            max_items: 最大抓取数量
            days_back: 往回拉取的天数 (默认 3)

        Returns:
            list[NormalizedItem]
        """
        max_items = kwargs.get("max_items", self.max_items)
        days_back = kwargs.get("days_back", 3)

        if max_items <= 0:
            self.logger.info("AIHOT max_items <= 0, 跳过抓取")
            return []

        self.logger.info("开始 AIHOT 数据抓取")

        all_items = []

        # 1. 拉取精选条目
        since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        items_data = self._fetch_items(
            mode="selected", take=max_items, since=since
        )
        for item_data in items_data:
            item = self._item_to_normalized(item_data, "aihot_news")
            all_items.append(item)

        # 2. 拉取最新日报
        daily_data = self._fetch_daily()
        if daily_data:
            sections = daily_data.get("sections", [])
            for section in sections:
                label = section.get("label", "")
                for item_data in section.get("items", []):
                    title = item_data.get("title", "")
                    url = item_data.get("sourceUrl", "")
                    summary = item_data.get("summary", "")

                    item = NormalizedItem(
                        source="aihot",
                        source_type="aihot_daily",
                        title=title,
                        url=url,
                        author=item_data.get("sourceName", "AIHOT"),
                        published_at=daily_data.get("generatedAt"),
                        summary=summary,
                        tags=["AI", "日报", *self._auto_tag(title, summary, None)],
                        score=15,  # 日报条目基础分较高
                        raw={
                            "section": label,
                            "date": daily_data.get("date"),
                        },
                    )
                    all_items.append(item)

            # 3. 快讯 (flashes)
            flashes = daily_data.get("flashes", [])
            for flash in flashes:
                item = NormalizedItem(
                    source="aihot",
                    source_type="aihot_daily",
                    title=flash.get("title", ""),
                    url=flash.get("sourceUrl", ""),
                    author=flash.get("sourceName", "AIHOT"),
                    published_at=flash.get("publishedAt"),
                    tags=["AI", "快讯"],
                    score=10,
                    raw={"type": "flash", "date": daily_data.get("date")},
                )
                all_items.append(item)

        # 4. 补充拉取部分分类精选（增加深度）
        for cat in ["ai-models", "ai-products", "industry"]:
            cat_items = self._fetch_items(
                mode="selected", category=cat, take=20, since=since
            )
            existing_urls = {item.url for item in all_items}
            for item_data in cat_items:
                if item_data.get("url") not in existing_urls:
                    item = self._item_to_normalized(item_data, "aihot_news")
                    all_items.append(item)
                    existing_urls.add(item_data.get("url"))

        self.logger.info(f"AIHOT 抓取完成: 共 {len(all_items)} 条")
        return all_items
