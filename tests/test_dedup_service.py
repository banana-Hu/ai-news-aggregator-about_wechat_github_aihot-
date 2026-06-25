"""去重服务测试。"""

import pytest
from ainews.schemas.normalized_item import NormalizedItem
from ainews.services.dedup_service import DedupService


class TestDedupService:
    """测试去重服务。"""

    def test_empty_list(self):
        svc = DedupService()
        result = svc.deduplicate([])
        assert result == []

    def test_no_duplicates(self):
        svc = DedupService()
        items = [
            NormalizedItem(source="github", source_type="github_repo",
                           title="repo1", url="https://github.com/a/repo1",
                           summary="First unique repo"),
            NormalizedItem(source="github", source_type="github_repo",
                           title="repo2", url="https://github.com/a/repo2",
                           summary="Second different repo"),
        ]
        result = svc.deduplicate(items)
        assert len(result) == 2

    def test_url_duplicate(self):
        svc = DedupService()
        items = [
            NormalizedItem(source="github", source_type="github_repo",
                           title="repo1", url="https://github.com/a/repo"),
            NormalizedItem(source="github", source_type="github_repo",
                           title="repo1-different", url="https://github.com/a/repo"),
        ]
        result = svc.deduplicate(items)
        assert len(result) == 1

    def test_title_duplicate(self):
        svc = DedupService()
        items = [
            NormalizedItem(source="aihot", source_type="aihot_news",
                           title="OpenAI发布新模型", url="https://example.com/1"),
            NormalizedItem(source="aihot", source_type="aihot_news",
                           title="OpenAI发布新模型", url="https://example.com/2"),
        ]
        result = svc.deduplicate(items)
        assert len(result) == 1

    def test_content_duplicate(self):
        svc = DedupService()
        items = [
            NormalizedItem(source="aihot", source_type="aihot_news",
                           title="Item 1", url="https://example.com/1",
                           summary="Same content here", content="Full body"),
            NormalizedItem(source="aihot", source_type="aihot_news",
                           title="Item 2", url="https://example.com/2",
                           summary="Same content here", content="Full body"),
        ]
        result = svc.deduplicate(items)
        assert len(result) == 1

    def test_mixed_sources(self):
        """跨数据源的重复也应被检测。"""
        svc = DedupService()
        items = [
            NormalizedItem(source="github", source_type="github_repo",
                           title="Agent Framework", url="https://github.com/agent/framework"),
            NormalizedItem(source="aihot", source_type="aihot_news",
                           title="Agent Framework", url="https://aihot.virxact.com/item/123"),
        ]
        result = svc.deduplicate(items)
        # 标题相同，title_hash 去重
        assert len(result) == 1

    def test_get_stats(self):
        svc = DedupService()
        items = [
            NormalizedItem(source="github", source_type="github_repo",
                           title="a", url="https://github.com/a/a"),
            NormalizedItem(source="github", source_type="github_repo",
                           title="a", url="https://github.com/b/b"),  # 标题重复
        ]
        svc.deduplicate(items)
        stats = svc.get_stats()
        assert stats["title_dup"] >= 1
        assert stats["kept"] >= 1

    def test_clear(self):
        svc = DedupService()
        items = [
            NormalizedItem(source="github", source_type="github_repo",
                           title="test", url="https://github.com/test"),
        ]
        svc.deduplicate(items)
        assert svc.get_stats()["kept"] == 1
        svc.clear()
        assert svc.get_stats()["kept"] == 0
