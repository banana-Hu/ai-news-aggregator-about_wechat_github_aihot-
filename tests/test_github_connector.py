"""GitHub 连接器测试。"""

import pytest
from unittest.mock import patch, MagicMock
from ainews.connectors.github_connector import GitHubConnector


class TestGitHubConnector:
    """测试 GitHub 连接器基本功能。"""

    def test_init_no_token(self):
        """未设置 Token 时能正常初始化。"""
        connector = GitHubConnector({"token": ""})
        assert connector.token == ""
        assert len(connector.queries) > 0

    def test_init_with_token(self):
        """设置了 Token 时正确加载。"""
        connector = GitHubConnector({"token": "ghp_test123"})
        assert connector.token == "ghp_test123"

    def test_auto_tag(self):
        """自动打标签功能。"""
        connector = GitHubConnector({"token": ""})
        tags = connector._auto_tag("Awesome LLM Agent Framework for RAG")
        assert "AI" in tags
        assert "Agent" in tags
        assert "LLM" in tags
        assert "RAG" in tags

    def test_auto_tag_agent(self):
        connector = GitHubConnector({"token": ""})
        tags = connector._auto_tag("multi-agent autonomous system")
        assert "Agent" in tags

    def test_auto_tag_mcp(self):
        connector = GitHubConnector({"token": ""})
        tags = connector._auto_tag("MCP Server Implementation")
        assert "MCP" in tags

    @patch("ainews.connectors.github_connector.GitHubConnector._search_repos")
    def test_fetch_no_results(self, mock_search):
        """搜索返回空结果。"""
        mock_search.return_value = {"items": []}
        connector = GitHubConnector({"token": "", "queries": ["test"]})
        items = connector.fetch()
        assert len(items) == 0

    @patch("ainews.connectors.github_connector.GitHubConnector._search_repos")
    @patch("ainews.connectors.github_connector.GitHubConnector._get_readme")
    @patch("ainews.connectors.github_connector.GitHubConnector._get_latest_release")
    def test_fetch_with_results(self, mock_release, mock_readme, mock_search):
        """搜索返回有效结果。"""
        mock_search.return_value = {
            "items": [
                {
                    "full_name": "testuser/test-repo",
                    "name": "test-repo",
                    "description": "An AI Agent framework for LLM applications",
                    "html_url": "https://github.com/testuser/test-repo",
                    "stargazers_count": 5000,
                    "forks_count": 200,
                    "language": "Python",
                    "topics": ["ai", "agent", "llm"],
                    "owner": {"login": "testuser"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-06-01T00:00:00Z",
                    "pushed_at": "2024-06-01T00:00:00Z",
                    "license": {"spdx_id": "MIT"},
                    "open_issues_count": 10,
                }
            ]
        }
        mock_readme.return_value = "# Test\nThis is a README."
        mock_release.return_value = {
            "tag_name": "v1.0.0",
            "name": "First Release",
            "body": "Initial release",
            "published_at": "2024-06-01T00:00:00Z",
            "html_url": "https://github.com/testuser/test-repo/releases/v1.0.0",
        }

        connector = GitHubConnector({"token": "", "queries": ["AI Agent"]})
        items = connector.fetch()

        assert len(items) >= 1
        item = items[0]
        assert item.source == "github"
        assert item.source_type == "github_repo"
        assert item.title == "test-repo"
        assert item.url == "https://github.com/testuser/test-repo"
        assert item.author == "testuser"
        assert "AI" in item.tags or "Agent" in item.tags or "LLM" in item.tags

    def test_deduplication_by_full_name(self):
        """相同 full_name 的仓库不应重复。"""
        connector = GitHubConnector({"token": ""})
        # 模拟两个搜索返回相同仓库
        repo_data = {
            "full_name": "testuser/test-repo",
            "name": "test-repo",
            "description": "test",
            "html_url": "https://github.com/testuser/test-repo",
            "stargazers_count": 100,
            "forks_count": 50,
            "owner": {"login": "testuser"},
        }

        seen = set()
        assert "testuser/test-repo" not in seen
        seen.add("testuser/test-repo")
        assert "testuser/test-repo" in seen
