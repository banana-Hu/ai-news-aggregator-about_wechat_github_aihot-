"""
去重服务。
基于 URL、标题、内容的哈希值进行三层去重。
"""

import hashlib
import logging
from typing import Iterator

from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)


class DedupService:
    """去重服务。

    维护三个哈希集合来检测重复：
    - url_hashes: URL 哈希
    - title_hashes: 标题哈希
    - content_hashes: 内容哈希
    """

    def __init__(self):
        self.url_hashes: set[str] = set()
        self.title_hashes: set[str] = set()
        self.content_hashes: set[str] = set()
        self._stats = {"url_dup": 0, "title_dup": 0, "content_dup": 0, "kept": 0}

    def is_duplicate(self, item: NormalizedItem) -> bool:
        """检查单条是否为重复。重复判定：URL / 标题 / 内容 任一匹配即视为重复。"""
        url_h = item.url_hash
        title_h = item.title_hash
        content_h = item.content_hash

        # URL 去重（最严格）
        if url_h in self.url_hashes:
            self._stats["url_dup"] += 1
            return True

        # 标题去重（标题为空时不判定）
        if title_h and title_h in self.title_hashes:
            self._stats["title_dup"] += 1
            return True

        # 内容去重（摘要+内容为空时不判定）
        if content_h and content_h in self.content_hashes:
            self._stats["content_dup"] += 1
            return True

        # 无重复，记录哈希
        self.url_hashes.add(url_h)
        if title_h:
            self.title_hashes.add(title_h)
        if content_h:
            self.content_hashes.add(content_h)
        self._stats["kept"] += 1
        return False

    def deduplicate(self, items: list[NormalizedItem]) -> list[NormalizedItem]:
        """对列表进行整体去重。"""
        # 重置统计
        self._stats = {"url_dup": 0, "title_dup": 0, "content_dup": 0, "kept": 0}

        result = []
        for item in items:
            if not self.is_duplicate(item):
                result.append(item)

        logger.info(
            f"去重完成: 输入 {len(items)} 条, "
            f"保留 {self._stats['kept']} 条, "
            f"重复 {self._stats['url_dup'] + self._stats['title_dup'] + self._stats['content_dup']} 条 "
            f"(URL重复={self._stats['url_dup']}, "
            f"标题重复={self._stats['title_dup']}, "
            f"内容重复={self._stats['content_dup']})"
        )
        return result

    def get_stats(self) -> dict:
        """获取去重统计。"""
        return dict(self._stats)

    def clear(self):
        """清空所有哈希集合。"""
        self.url_hashes.clear()
        self.title_hashes.clear()
        self.content_hashes.clear()
        self._stats = {"url_dup": 0, "title_dup": 0, "content_dup": 0, "kept": 0}
