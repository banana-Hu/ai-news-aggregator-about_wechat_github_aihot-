"""
GitHub 数据源连接器。
通过 GitHub Search API 搜索 AI 相关开源项目，获取仓库信息、README、Release 等。
"""

import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterator
from urllib.parse import quote

import requests

from .base import BaseConnector
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# 默认搜索关键词
DEFAULT_QUERIES = [
    "AI Agent",
    "LLM",
    "RAG",
    "MCP",
    "AI coding",
    "workflow automation",
    "Claude Code",
    "OpenAI",
    "multi-agent",
    "local LLM",
    "prompt engineering",
    "AI tool",
    "function calling",
    "AI workflow",
    "autonomous agent",
]

# 用于自动打标签的关键词映射
TAG_KEYWORDS = {
    "AI": ["ai", "artificial intelligence", "llm", "gpt", "claude", "openai", "chatgpt"],
    "Agent": ["agent", "multi-agent", "autonomous", "tool use", "function calling"],
    "LLM": ["llm", "language model", "gpt", "claude", "mistral", "llama", "gemini"],
    "RAG": ["rag", "retrieval augmented", "vector search", "embedding", "knowledge base"],
    "MCP": ["mcp", "model context protocol"],
    "Coding": ["ai coding", "code generation", "copilot", "code assistant", "cursor"],
    "Workflow": ["workflow", "automation", "pipeline", "orchestration"],
    "Open Source": ["open source", "oss"],
}


class GitHubConnector(BaseConnector):
    """GitHub 数据源连接器。"""

    BASE_URL = "https://api.github.com"
    SEARCH_REPO_URL = f"{BASE_URL}/search/repositories"
    REPO_URL = f"{BASE_URL}/repos"
    RATE_LIMIT_URL = f"{BASE_URL}/rate_limit"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.token = config.get("token") or os.environ.get("GITHUB_TOKEN", "")
        self.queries = config.get("queries", DEFAULT_QUERIES)
        self.max_per_query = config.get("max_per_query", 10)
        self.sort = config.get("sort", "stars")
        self.order = config.get("order", "desc")
        self.max_retries = config.get("max_retries", 3)
        self.request_timeout = config.get("request_timeout", 15)
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-News-Aggregator/1.0",
        })
        if self.token:
            session.headers.update({"Authorization": f"token {self.token}"})
            self.logger.info("使用 GitHub Token 认证（已隐藏具体值）")
        else:
            self.logger.warning("未设置 GITHUB_TOKEN，将使用未认证模式（速率限制: 60 req/h）")
        return session

    def _check_rate_limit(self) -> dict:
        """检查当前 API 速率限制状态。"""
        try:
            resp = self._session.get(self.RATE_LIMIT_URL, timeout=self.request_timeout)
            if resp.status_code == 200:
                return resp.json().get("resources", {}).get("core", {})
        except Exception:
            pass
        return {}

    def _search_repos(self, query: str, page: int = 1) -> Optional[dict]:
        """执行一次仓库搜索。"""
        per_page = min(self.max_per_query, 100)
        params = {
            "q": query,
            "sort": self.sort,
            "order": self.order,
            "per_page": per_page,
            "page": page,
        }
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(
                    self.SEARCH_REPO_URL,
                    params=params,
                    timeout=self.request_timeout,
                )
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 403:
                    # 速率限制
                    self.logger.warning(f"速率限制触发 (query={query}), 等待重试...")
                    self.rate_limit_sleep(60)
                    continue
                elif resp.status_code == 422:
                    self.logger.error(f"搜索参数无效 (query={query}): {resp.text}")
                    return None
                else:
                    self.logger.warning(f"搜索返回 {resp.status_code} (query={query}): {resp.text[:200]}")
                    if attempt < self.max_retries - 1:
                        self.rate_limit_sleep(2 ** attempt)
            except requests.exceptions.Timeout:
                self.logger.warning(f"请求超时 (query={query}, attempt={attempt + 1})")
                if attempt < self.max_retries - 1:
                    self.rate_limit_sleep(2 ** attempt)
            except requests.exceptions.ConnectionError as e:
                self.logger.warning(f"连接错误 (query={query}): {e}")
                if attempt < self.max_retries - 1:
                    self.rate_limit_sleep(5)
            except Exception as e:
                self.logger.error(f"搜索异常 (query={query}): {e}")
                return None
        return None

    def _get_repo_detail(self, full_name: str) -> Optional[dict]:
        """获取仓库详细信息。"""
        url = f"{self.REPO_URL}/{full_name}"
        try:
            resp = self._session.get(url, timeout=self.request_timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.logger.debug(f"获取仓库详情失败 {full_name}: {e}")
        return None

    def _get_readme(self, full_name: str) -> Optional[str]:
        """获取仓库 README 内容。"""
        url = f"{self.REPO_URL}/{full_name}/readme"
        try:
            resp = self._session.get(url, timeout=self.request_timeout, headers={
                **self._session.headers,
                "Accept": "application/vnd.github.v3.raw",
            })
            if resp.status_code == 200:
                text = resp.text
                # 截断过长的 README
                if len(text) > 5000:
                    text = text[:5000] + "\n\n... [READ MORE: README truncated at 5000 chars]"
                return text
        except Exception as e:
            self.logger.debug(f"获取 README 失败 {full_name}: {e}")
        return None

    def _get_latest_release(self, full_name: str) -> Optional[dict]:
        """获取仓库最新 Release。"""
        url = f"{self.REPO_URL}/{full_name}/releases/latest"
        try:
            resp = self._session.get(url, timeout=self.request_timeout)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "tag_name": data.get("tag_name", ""),
                    "name": data.get("name", ""),
                    "body": data.get("body", "")[:2000],
                    "published_at": data.get("published_at", ""),
                    "html_url": data.get("html_url", ""),
                }
        except Exception:
            pass
        return None

    def _auto_tag(self, text: str) -> list[str]:
        """根据标题和简介自动打标签。"""
        text_lower = text.lower()
        tags = []
        for tag, keywords in TAG_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    tags.append(tag)
                    break
        return tags if tags else ["AI"]

    def _repo_to_item(self, repo: dict) -> NormalizedItem:
        """将 GitHub API 返回的仓库数据转为 NormalizedItem。"""
        full_name = repo.get("full_name", "")
        name = repo.get("name", "")
        description = repo.get("description") or ""
        html_url = repo.get("html_url", "")
        owner_login = ""
        if repo.get("owner"):
            owner_login = repo["owner"].get("login", "")

        # 获取 README
        readme_content = ""
        if full_name:
            readme_content = self._get_readme(full_name) or ""

        # 获取 Release
        latest_release = None
        if full_name:
            latest_release = self._get_latest_release(full_name)

        # 生成摘要
        summary = description
        if latest_release:
            summary += f" | 最新 Release: {latest_release.get('tag_name', '')} - {latest_release.get('name', '')}"

        # 标签
        tag_text = f"{name} {description}"
        tags = self._auto_tag(tag_text)

        # 发布时间
        published_at = repo.get("created_at")
        updated_at = repo.get("updated_at")
        pushed_at = repo.get("pushed_at")

        # 原始数据
        raw = {
            "full_name": full_name,
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "license": repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
            "open_issues": repo.get("open_issues_count", 0),
            "updated_at": updated_at,
            "pushed_at": pushed_at,
            "created_at": published_at,
            "has_readme": bool(readme_content),
            "latest_release": latest_release,
        }

        return NormalizedItem(
            source="github",
            source_type="github_repo",
            title=name,
            url=html_url,
            author=owner_login,
            published_at=published_at,
            summary=summary,
            content=readme_content,
            tags=tags,
            score=0,
            raw=raw,
        )

    def _release_to_item(self, repo_item: NormalizedItem, release: dict) -> NormalizedItem:
        """将 Release 信息转为 NormalizedItem。"""
        return NormalizedItem(
            source="github",
            source_type="github_release",
            title=f"{repo_item.title} {release.get('tag_name', '')}",
            url=release.get("html_url", repo_item.url),
            author=repo_item.author,
            published_at=release.get("published_at"),
            summary=release.get("name", "") or release.get("tag_name", ""),
            content=release.get("body", ""),
            tags=repo_item.tags,
            score=0,
            raw={
                "repo_full_name": repo_item.raw.get("full_name", ""),
                "tag_name": release.get("tag_name", ""),
                "release_name": release.get("name", ""),
            },
        )

    def fetch(self, **kwargs) -> list[NormalizedItem]:
        """执行 GitHub 数据抓取。

        Args:
            queries: 可选，覆盖默认搜索关键词列表。
            max_per_query: 可选，覆盖每个关键词最大抓取数。

        Returns:
            list[NormalizedItem]: 标准化数据条目列表。
        """
        queries = kwargs.get("queries", self.queries)
        max_per_query = kwargs.get("max_per_query", self.max_per_query)

        self.logger.info(f"开始 GitHub 数据抓取: {len(queries)} 个关键词, 每个最多 {max_per_query} 条")

        # 检查速率限制
        rate_info = self._check_rate_limit()
        if rate_info:
            remaining = rate_info.get("remaining", 0)
            reset_time = rate_info.get("reset", 0)
            self.logger.info(f"API 剩余配额: {remaining} 次")
            if remaining < 10:
                self.logger.warning("API 配额即将耗尽，抓取可能不完整")

        seen_names = set()
        items = []

        for query in queries:
            self.logger.info(f"搜索关键词: {query}")
            result = self._search_repos(query)
            if not result:
                continue

            repos = result.get("items", [])
            self.logger.info(f"  获取到 {len(repos)} 个结果")

            for repo in repos:
                full_name = repo.get("full_name", "")
                if not full_name or full_name in seen_names:
                    continue
                seen_names.add(full_name)

                item = self._repo_to_item(repo)
                items.append(item)

                # 如果有 Release，也加入
                latest_release = item.raw.get("latest_release")
                if latest_release:
                    release_item = self._release_to_item(item, latest_release)
                    items.append(release_item)

                self.rate_limit_sleep(0.3)  # 避免触发次级限流

            # 避免过于频繁请求
            if len(queries) > 1:
                self.rate_limit_sleep(0.5)

        self.logger.info(f"GitHub 抓取完成: 共 {len(items)} 条 (仓库 + Release)")
        return items
