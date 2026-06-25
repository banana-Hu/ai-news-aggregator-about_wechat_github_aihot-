"""NormalizedItem 单元测试。"""

import pytest
from ainews.schemas.normalized_item import NormalizedItem


class TestNormalizedItem:
    """测试 NormalizedItem 基本功能。"""

    def test_basic_creation(self):
        item = NormalizedItem(
            source="github",
            source_type="github_repo",
            title="test-repo",
            url="https://github.com/test/test-repo",
        )
        assert item.source == "github"
        assert item.source_type == "github_repo"
        assert item.title == "test-repo"
        assert item.fetched_at is not None  # 自动填充
        assert item.score == 0

    def test_url_hash(self):
        item1 = NormalizedItem(
            source="github", source_type="github_repo",
            title="repo1", url="https://github.com/a/b",
        )
        item2 = NormalizedItem(
            source="github", source_type="github_repo",
            title="repo2", url="https://github.com/a/b",
        )
        assert item1.url_hash == item2.url_hash

    def test_title_hash_case_insensitive(self):
        item1 = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="Hello World", url="https://example.com/1",
        )
        item2 = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="hello world", url="https://example.com/2",
        )
        assert item1.title_hash == item2.title_hash

    def test_content_hash(self):
        item1 = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="Test", url="https://example.com/1",
            summary="Some summary", content="Some content",
        )
        item2 = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="Test", url="https://example.com/2",
            summary="some summary", content="some content",
        )
        assert item1.content_hash == item2.content_hash

    def test_to_dict_and_from_dict(self):
        original = NormalizedItem(
            source="github", source_type="github_repo",
            title="my-repo", url="https://github.com/u/my-repo",
            author="u", tags=["AI", "Agent"],
            score=85,
        )
        d = original.to_dict()
        restored = NormalizedItem.from_dict(d)
        assert restored.source == original.source
        assert restored.title == original.title
        assert restored.tags == original.tags
        assert restored.score == original.score

    def test_fetched_at_auto_fill(self):
        item = NormalizedItem(
            source="github", source_type="github_repo",
            title="test", url="https://github.com/test",
        )
        assert item.fetched_at != ""
        assert "T" in item.fetched_at  # ISO format
