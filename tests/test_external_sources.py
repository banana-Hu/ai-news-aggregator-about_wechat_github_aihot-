"""
集成测试。
测试完整数据流：抓取 → 去重 → 评分 → 输出。
"""

import pytest
from unittest.mock import patch, MagicMock
from ainews.schemas.normalized_item import NormalizedItem
from ainews.services.dedup_service import DedupService
from ainews.services.scoring_service import ScoringService


class TestFullPipeline:
    """测试完整数据处理流水线。"""

    def test_full_pipeline(self):
        """模拟完整数据流程。"""
        # 模拟 GitHub 数据
        github_items = [
            NormalizedItem(
                source="github", source_type="github_repo",
                title="agent-framework", url="https://github.com/u/agent",
                author="u",
                summary="A powerful AI Agent framework",
                tags=["AI", "Agent"],
                raw={"stars": 5000, "has_readme": True, "latest_release": {"tag": "v1"}},
            ),
            NormalizedItem(
                source="github", source_type="github_repo",
                title="llm-toolkit", url="https://github.com/u/llm",
                author="u",
                summary="LLM toolkit for production",
                tags=["AI", "LLM"],
                raw={"stars": 200, "has_readme": False},
            ),
        ]

        # 模拟 AIHOT 数据
        aihot_items = [
            NormalizedItem(
                source="aihot", source_type="aihot_news",
                title="OpenAI发布GPT-5", url="https://openai.com/blog/gpt-5",
                author="OpenAI",
                summary="最新GPT-5模型发布",
            ),
            NormalizedItem(
                source="aihot", source_type="aihot_daily",
                title="Agent Framework review", url="https://example.com/agent",
                author="Some Blog",
                summary="Review of the new agent framework",
            ),
        ]

        # 合并
        all_items = github_items + aihot_items
        assert len(all_items) == 4

        # 去重
        dedup = DedupService()
        deduped = dedup.deduplicate(all_items)
        assert len(deduped) == 4  # 没有重复

        # 评分
        scored = ScoringService.score_all(deduped)
        assert len(scored) == 4
        # agent-framework 评分应该最高（高 stars + readme + release + keyword）
        assert scored[0].score >= scored[1].score

    def test_pipeline_with_duplicates(self):
        """重复数据处理。"""
        items = [
            NormalizedItem(
                source="github", source_type="github_repo",
                title="same-repo", url="https://github.com/u/repo",
                summary="Unique summary A",
            ),
            NormalizedItem(
                source="github", source_type="github_repo",
                title="same-repo", url="https://github.com/u/repo-copy",
                summary="Unique summary A",  # same content → content dup
            ),
            NormalizedItem(
                source="aihot", source_type="aihot_news",
                title="Different Title", url="https://example.com/1",
                summary="Another unique summary B",
            ),
            NormalizedItem(
                source="aihot", source_type="aihot_daily",
                title="Different Title duplicate",
                url="https://example.com/2",
                summary="Another unique summary B",  # same content → content dup of item3
            ),
        ]

        dedup = DedupService()
        deduped = dedup.deduplicate(items)
        # 4条输入：第2条内容重复，第4条内容重复 → 保留2条
        assert len(deduped) == 2

    def test_pipeline_empty(self):
        """空数据流。"""
        dedup = DedupService()
        deduped = dedup.deduplicate([])
        assert deduped == []

        scored = ScoringService.score_all([])
        assert scored == []

    def test_cross_source_dedup(self):
        """跨数据源去重（相同标题）。"""
        items = [
            NormalizedItem(
                source="github", source_type="github_repo",
                title="MCP Server", url="https://github.com/u/mcp",
            ),
            NormalizedItem(
                source="aihot", source_type="aihot_news",
                title="MCP Server", url="https://aihot.virxact.com/item/mcp",
            ),
        ]
        dedup = DedupService()
        deduped = dedup.deduplicate(items)
        # 标题相同，标题哈希去重
        assert len(deduped) == 1
