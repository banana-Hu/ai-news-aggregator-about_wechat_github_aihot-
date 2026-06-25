"""AIHOT 连接器测试。"""

import pytest
from unittest.mock import patch, MagicMock
from ainews.connectors.aihot_connector import AIHOTConnector


class TestAIHOTConnector:
    """测试 AIHOT 连接器基本功能。"""

    def test_init(self):
        connector = AIHOTConnector({})
        assert connector.base_url == "https://aihot.virxact.com"
        assert "aihot-skill" in connector.user_agent

    @patch("ainews.connectors.aihot_connector.AIHOTConnector._request")
    def test_fetch_items_selected(self, mock_request):
        """拉取精选条目。"""
        mock_request.return_value = {
            "count": 2,
            "items": [
                {
                    "id": "cm9abc123",
                    "title": "OpenAI发布GPT-5",
                    "title_en": "OpenAI releases GPT-5",
                    "url": "https://openai.com/blog/gpt-5",
                    "source": "OpenAI Blog",
                    "publishedAt": "2026-06-24T01:00:00.000Z",
                    "summary": "OpenAI发布了最新的GPT-5模型...",
                    "category": "ai-models",
                    "score": 95,
                    "selected": True,
                },
                {
                    "id": "cm9abc124",
                    "title": "Claude Code 发布新版本",
                    "url": "https://anthropic.com/news/claude-code",
                    "source": "Anthropic",
                    "publishedAt": "2026-06-23T15:30:00.000Z",
                    "summary": "Anthropic推出Claude Code新功能...",
                    "category": "ai-products",
                    "score": 88,
                    "selected": True,
                },
            ]
        }
        connector = AIHOTConnector({"max_items": 50})
        items = connector.fetch()

        assert len(items) >= 2
        # 验证第一条
        item1 = items[0]
        assert item1.source == "aihot"
        assert item1.source_type == "aihot_news"
        assert "GPT-5" in item1.title
        assert item1.url == "https://openai.com/blog/gpt-5"
        assert item1.author == "OpenAI Blog"

    @patch("ainews.connectors.aihot_connector.AIHOTConnector._request")
    def test_fetch_daily(self, mock_request):
        """拉取日报。"""
        # items 端点返回空（避免干扰日报测试）
        def mock_side_effect(path, params=None):
            if "items" in path:
                return {"count": 0, "items": []}
            elif "daily" in path:
                return {
                    "date": "2026-06-24",
                    "generatedAt": "2026-06-24T00:01:23.456Z",
                    "sections": [
                        {
                            "label": "模型发布/更新",
                            "items": [
                                {
                                    "title": "FastWan-QAD发布",
                                    "sourceUrl": "https://example.com/fastwan",
                                    "sourceName": "Sky Computing Lab",
                                    "summary": "单卡5090上1.8秒生成5秒视频",
                                }
                            ],
                        }
                    ],
                    "flashes": [
                        {
                            "title": "快讯：某模型发布",
                            "sourceUrl": "https://example.com/flash",
                            "sourceName": "X平台",
                            "publishedAt": "2026-06-23T10:00:00Z",
                        }
                    ],
                }
            return None

        mock_request.side_effect = mock_side_effect
        connector = AIHOTConnector({"max_items": 50})
        items = connector.fetch()

        assert len(items) >= 2  # at least 1 section item + 1 flash
        daily_items = [i for i in items if i.source_type == "aihot_daily"]
        assert len(daily_items) >= 2

    @patch("ainews.connectors.aihot_connector.AIHOTConnector._request")
    def test_fetch_with_no_daily(self, mock_request):
        """日报不存在时不应崩溃。"""
        def mock_side_effect(path, params=None):
            if "items" in path:
                return {"count": 1, "items": [
                    {
                        "id": "test1",
                        "title": "Test Item",
                        "url": "https://example.com/test",
                        "source": "Test",
                        "publishedAt": "2026-06-24T00:00:00Z",
                        "summary": "Test summary",
                        "selected": True,
                    }
                ]}
            elif "daily" in path:
                return None  # 日报不存在
            return None

        mock_request.side_effect = mock_side_effect
        connector = AIHOTConnector({"max_items": 50})
        items = connector.fetch()
        assert len(items) >= 1

    def test_auto_tag(self):
        connector = AIHOTConnector({})
        tags = connector._auto_tag(
            "OpenAI GPT-5 正式发布",
            "OpenAI发布了下一代大模型",
            "ai-models",
        )
        assert "AI" in tags
        # OPENAI tag should exist (lowercase matching in auto_tag)
        assert any("OPENAI" in t.upper() for t in tags)

    def test_auto_tag_agent(self):
        connector = AIHOTConnector({})
        tags = connector._auto_tag(
            "Agent Framework 发布",
            "一个全新的AI Agent框架",
            "ai-products",
        )
        assert "Agent" in tags or "AI" in tags

    def test_auto_tag_rag(self):
        connector = AIHOTConnector({})
        tags = connector._auto_tag(
            "RAG系统优化实践",
            "本文讨论了RAG检索增强生成的优化方法",
        )
        assert "RAG" in tags
