"""
统一标准化数据结构。
所有外部信息源（GitHub、AIHOT 等）必须输出此格式。
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import hashlib


@dataclass
class NormalizedItem:
    """统一的外部信息条目结构。

    Attributes:
        source: 数据源标识，如 "github" / "aihot"
        source_type: 数据子类型，如 "github_repo" / "github_release" / "aihot_news" / "aihot_daily"
        title: 内容标题
        url: 原始链接
        author: 作者、仓库 owner 或来源名称
        published_at: 发布时间，ISO 格式字符串或 None
        fetched_at: 抓取时间，ISO 格式字符串
        summary: 原始简介或初步摘要
        content: 正文或 README 内容
        tags: 标签列表
        score: 基础评分（0-100）
        raw: 原始数据（保留原始抓取结果，用于调试和后续处理）
    """
    source: str
    source_type: str
    title: str
    url: str
    author: str = ""
    published_at: Optional[str] = None
    fetched_at: str = ""
    summary: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    score: int = 0
    raw: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()

    @property
    def url_hash(self) -> str:
        """基于 URL 的 SHA256 哈希，用于去重。"""
        return hashlib.sha256(self.url.encode("utf-8")).hexdigest()

    @property
    def title_hash(self) -> str:
        """基于标题的 SHA256 哈希，用于去重。"""
        return hashlib.sha256(self.title.strip().lower().encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        """基于摘要+内容的 SHA256 哈希，用于去重。"""
        text = (self.summary + " " + self.content).strip().lower()
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        """转为 JSON 可序列化字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NormalizedItem":
        """从字典恢复。"""
        return cls(**data)
