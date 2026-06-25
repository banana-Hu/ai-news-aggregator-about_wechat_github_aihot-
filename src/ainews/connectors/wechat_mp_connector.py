"""
公众号 (WeChat Official Account) 文章连接器。

数据来源优先级：
1. AIHOT items API 关键词搜索 → 发现最新公众号文章
2. 用户配置的指定公众号 → 定向抓取
3. 单篇文章 URL 直接输入

所有文章输出为 NormalizedItem，并提取正文纯文本。
"""

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from .base import BaseConnector
from .mp_extractor import extract_article_content, is_wechat_article
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# AIHOT API 配置
AIHOT_BASE = "https://aihot.virxact.com"
AIHOT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 aihot-skill/0.2.0"
)

# 默认搜索关键词（用于发现公众号文章）
DEFAULT_SEARCH_KEYWORDS = [
    "AI", "Agent", "LLM", "大模型", "OpenAI", "Claude",
    "ChatGPT", "创业", "科技", "AI 产品", "模型",
]

# 标签关键词映射
TAG_KEYWORDS = {
    "AI": ["ai", "人工智能", "大模型", "llm", "gpt", "claude", "openai"],
    "Agent": ["agent", "智能体", "ai agent"],
    "LLM": ["llm", "大模型", "语言模型"],
    "产品": ["产品", "发布", "上线", "新品"],
    "行业": ["行业", "融资", "投资", "收购", "市场"],
    "技术": ["技术", "架构", "算法", "论文", "研究"],
    "创业": ["创业", "startup", "融资"],
    "观点": ["观点", "思考", "深度", "分析"],
}


class WeChatMpConnector(BaseConnector):
    """公众号文章连接器。"""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.search_keywords = config.get("search_keywords", DEFAULT_SEARCH_KEYWORDS)
        self.accounts = config.get("accounts", [])  # 用户关注的公众号列表
        self.max_articles = config.get("max_articles", 30)
        self.days_back = config.get("days_back", 3)
        self.extract_content = config.get("extract_content", True)
        self.aihot_ua = config.get("aihot_user_agent", AIHOT_UA)
        self.max_retries = config.get("max_retries", 3)
        self.request_timeout = config.get("request_timeout", 15)
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.aihot_ua,
            "Accept": "application/json",
        })
        return session

    def _search_aihot_items(self, query: str, take: int = 20) -> list[dict]:
        """通过 AIHOT items API 搜索文章。"""
        url = f"{AIHOT_BASE}/api/public/items"
        params = {"q": query, "mode": "all", "take": min(take, 100)}

        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self.request_timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    # 只保留公众号文章链接
                    mp_items = [
                        i for i in items
                        if i.get("url") and "mp.weixin.qq.com" in i["url"]
                    ]
                    if mp_items:
                        self.logger.debug(f"AIHOT '{query}' → {len(mp_items)} 条公众号文章")
                    return mp_items
                elif resp.status_code == 429:
                    self.rate_limit_sleep(5 * (attempt + 1))
                else:
                    self.logger.debug(f"AIHOT 搜索返回 {resp.status_code}: {query}")
                    if attempt < self.max_retries - 1:
                        self.rate_limit_sleep(2 ** attempt)
            except Exception as e:
                self.logger.debug(f"AIHOT 搜索异常: {query}, {e}")
                if attempt < self.max_retries - 1:
                    self.rate_limit_sleep(2 ** attempt)
        return []

    def _tag_article(self, title: str, content: str) -> list[str]:
        """给文章打标签。"""
        text = f"{title} {content[:500]}".lower()
        tags = []
        for tag, keywords in TAG_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    tags.append(tag)
                    break
        if "公众号" in tags:
            tags.remove("公众号")
        return tags if tags else ["AI"]

    def _discover_from_aihot(self) -> list[dict]:
        """从 AIHOT 发现公众号文章。"""
        discovered = []
        seen_urls = set()

        for keyword in self.search_keywords:
            items = self._search_aihot_items(keyword, take=20)
            for item in items:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    discovered.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "author": item.get("source", ""),
                        "published_at": item.get("publishedAt"),
                        "summary": item.get("summary", ""),
                        "source_discovery": f"aihot:{keyword}",
                    })
            self.rate_limit_sleep(0.3)  # 防止限流

        self.logger.info(f"AIHOT 发现 {len(discovered)} 条公众号文章")
        return discovered

    def _build_author_urls(self) -> list[str]:
        """构建指定公众号的文章搜索 URL（通过关键词搜索）。"""
        urls = set()
        for account in self.accounts:
            name = account.get("name", "")
            gh_id = account.get("gh_id", "")
            if name:
                # 通过 AIHOT 搜索公众号名称
                items = self._search_aihot_items(name, take=20)
                for item in items:
                    url = item.get("url", "")
                    if url and "mp.weixin.qq.com" in url:
                        urls.add(url)
                self.rate_limit_sleep(0.3)
        self.logger.info(f"指定公众号发现 {len(urls)} 条")
        return list(urls)

    def fetch(self, **kwargs) -> list[NormalizedItem]:
        """执行公众号文章抓取。

        流程：
        1. 从 AIHOT 发现公众号文章 URL
        2. 从用户指定公众号搜索文章
        3. 对每篇文章提取正文
        4. 统一输出 NormalizedItem

        Args:
            extract_content: 是否提取完整正文（需下载页面）

        Returns:
            list[NormalizedItem]
        """
        extract_content = kwargs.get("extract_content", self.extract_content)
        max_articles = kwargs.get("max_articles", self.max_articles)

        self.logger.info("开始公众号文章抓取")

        # 1. 发现文章
        discovered = self._discover_from_aihot()

        # 2. 补充指定公众号
        if self.accounts:
            account_urls = self._build_author_urls()
            existing_urls = {d["url"] for d in discovered}
            for url in account_urls:
                if url not in existing_urls:
                    discovered.append({
                        "title": "",
                        "url": url,
                        "author": "",
                        "published_at": None,
                        "summary": "",
                        "source_discovery": "user_account",
                    })

        self.logger.info(f"共发现 {len(discovered)} 条待处理文章")

        # 限制处理数量
        discovered = discovered[:max_articles]

        # 3. 提取正文并转换为 NormalizedItem
        items = []
        for i, entry in enumerate(discovered):
            url = entry["url"]
            self.logger.info(f"处理 [{i+1}/{len(discovered)}]: {url}")

            item = self._entry_to_item(entry)

            # 提取正文
            if extract_content:
                article = extract_article_content(url)
                if article:
                    item.title = article.get("title") or item.title
                    item.author = article.get("author") or item.author
                    item.content = article.get("content_text", "")
                    item.raw["content_html"] = article.get("content_html", "")[:2000]
                    item.raw["cover_url"] = article.get("cover_url", "")
                else:
                    self.logger.warning(f"正文提取失败: {url}")
                    item.raw["extract_error"] = True

            # 标签
            item.tags = self._tag_article(item.title, item.content or item.summary)

            items.append(item)

        self.logger.info(f"公众号文章抓取完成: {len(items)} 条")
        return items

    def _entry_to_item(self, entry: dict) -> NormalizedItem:
        """将发现条目转为 NormalizedItem（不含正文提取）。"""
        return NormalizedItem(
            source="wechat_mp",
            source_type="wechat_article",
            title=entry.get("title", "公众号文章"),
            url=entry.get("url", ""),
            author=entry.get("author", ""),
            published_at=entry.get("published_at"),
            summary=entry.get("summary", ""),
            tags=["AI"],
            score=0,
            raw={
                "source_discovery": entry.get("source_discovery", ""),
            },
        )

    @staticmethod
    def fetch_single_article(url: str, extract_content: bool = True) -> Optional[NormalizedItem]:
        """抓取单篇公众号文章。

        便捷静态方法，不依赖实例配置。
        """
        if not is_wechat_article(url):
            logger.warning(f"非公众号文章: {url}")
            return None

        item = NormalizedItem(
            source="wechat_mp",
            source_type="wechat_article",
            title="公众号文章",
            url=url,
        )

        if extract_content:
            article = extract_article_content(url)
            if article:
                item.title = article.get("title", "")
                item.author = article.get("author", "")
                item.content = article.get("content_text", "")
                item.raw["cover_url"] = article.get("cover_url", "")
            else:
                return None

        return item
