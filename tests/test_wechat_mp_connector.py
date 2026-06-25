"""公众号连接器测试。"""

import pytest
from unittest.mock import patch, MagicMock
from ainews.connectors.wechat_mp_connector import WeChatMpConnector
from ainews.connectors.mp_extractor import is_wechat_article, extract_article_content


class TestMpExtractor:
    """测试正文提取工具。"""

    def test_is_wechat_article_true(self):
        assert is_wechat_article("https://mp.weixin.qq.com/s/abc123")
        assert is_wechat_article("https://mp.weixin.qq.com/s/abc123?some=param")

    def test_is_wechat_article_false(self):
        assert not is_wechat_article("https://github.com/user/repo")
        assert not is_wechat_article("https://example.com/article")
        assert not is_wechat_article("")

    def test_is_wechat_article_mp_but_no_s(self):
        """mp.weixin.qq.com 但没有 /s/ 路径。"""
        assert not is_wechat_article("https://mp.weixin.qq.com/profile")
        assert not is_wechat_article("https://mp.weixin.qq.com/mp/profile")


class TestWeChatMpConnector:
    """测试公众号连接器。"""

    def test_init_defaults(self):
        connector = WeChatMpConnector({})
        assert len(connector.search_keywords) > 0
        assert connector.accounts == []
        assert connector.max_articles == 30
        assert connector.extract_content is True

    def test_init_with_config(self):
        connector = WeChatMpConnector({
            "search_keywords": ["AI", "大模型"],
            "max_articles": 10,
            "extract_content": False,
            "accounts": [{"name": "测试号", "gh_id": "gh_test"}],
        })
        assert len(connector.search_keywords) == 2
        assert len(connector.accounts) == 1
        assert connector.max_articles == 10
        assert connector.extract_content is False

    def test_tag_article(self):
        connector = WeChatMpConnector({})
        tags = connector._tag_article(
            "OpenAI 发布 GPT-5，Agent 能力大幅提升",
            "OpenAI 今天发布了最新的 GPT-5 模型，引入了全新的 Agent 能力..."
        )
        assert "AI" in tags or "Agent" in tags

    def test_tag_article_no_content(self):
        connector = WeChatMpConnector({})
        tags = connector._tag_article("测试标题", "")
        assert tags  # 至少返回 ["AI"]

    @patch("ainews.connectors.wechat_mp_connector.WeChatMpConnector._search_aihot_items")
    def test_discover_from_aihot(self, mock_search):
        """模拟 AIHOT 发现。"""
        mock_search.return_value = [
            {
                "title": "AI Agent 最新进展",
                "url": "https://mp.weixin.qq.com/s/test1",
                "source": "公众号：测试号",
                "publishedAt": "2026-06-24T10:00:00Z",
                "summary": "AI Agent 领域的最新进展",
            },
            {
                "title": "LLM 应用实践",
                "url": "https://mp.weixin.qq.com/s/test2",
                "source": "公众号：技术号",
                "publishedAt": "2026-06-23T08:00:00Z",
                "summary": "LLM 在生产环境的实践",
            },
        ]
        connector = WeChatMpConnector({"search_keywords": ["AI"], "extract_content": False})
        items = connector.fetch()
        assert len(items) == 2
        assert items[0].source == "wechat_mp"
        assert items[0].source_type == "wechat_article"
        assert "mp.weixin.qq.com" in items[0].url
        assert items[0].title == "AI Agent 最新进展"

    @patch("ainews.connectors.wechat_mp_connector.WeChatMpConnector._search_aihot_items")
    def test_empty_discovery(self, mock_search):
        """无发现结果。"""
        mock_search.return_value = []
        connector = WeChatMpConnector({"search_keywords": ["nothing"]})
        items = connector.fetch()
        assert len(items) == 0

    def test_fetch_single_article_invalid_url(self):
        """无效 URL 返回 None。"""
        result = WeChatMpConnector.fetch_single_article(
            "https://example.com/not-wechat", extract_content=False
        )
        assert result is None

    @patch("ainews.connectors.wechat_mp_connector.is_wechat_article")
    @patch("ainews.connectors.wechat_mp_connector.extract_article_content")
    def test_fetch_single_article_success(self, mock_extract, mock_is_wechat):
        """单篇文章抓取。"""
        mock_is_wechat.return_value = True
        mock_extract.return_value = {
            "title": "测试文章标题",
            "content_text": "这是文章正文内容...",
            "content_html": "<p>文章正文</p>",
            "author": "测试公众号",
            "cover_url": "https://example.com/cover.jpg",
        }
        result = WeChatMpConnector.fetch_single_article(
            "https://mp.weixin.qq.com/s/test"
        )
        assert result is not None
        assert result.source == "wechat_mp"
        assert result.title == "测试文章标题"
        assert result.author == "测试公众号"
        assert "文章正文" in result.content
        assert result.raw.get("cover_url") == "https://example.com/cover.jpg"

    @patch("ainews.connectors.wechat_mp_connector.is_wechat_article")
    @patch("ainews.connectors.wechat_mp_connector.extract_article_content")
    def test_fetch_single_article_failed_extract(self, mock_extract, mock_is_wechat):
        """提取失败返回 None。"""
        mock_is_wechat.return_value = True
        mock_extract.return_value = None
        result = WeChatMpConnector.fetch_single_article(
            "https://mp.weixin.qq.com/s/fail"
        )
        assert result is None
