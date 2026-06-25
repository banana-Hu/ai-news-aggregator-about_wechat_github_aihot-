"""评分服务测试。"""

import pytest
from datetime import datetime, timezone, timedelta
from ainews.schemas.normalized_item import NormalizedItem
from ainews.services.scoring_service import ScoringService


class TestScoringService:
    """测试评分服务。"""

    def test_github_low_stars(self):
        item = NormalizedItem(
            source="github", source_type="github_repo",
            title="small-repo", url="https://github.com/u/small",
            raw={"stars": 100, "has_readme": False},
        )
        score = ScoringService.score(item)
        assert score == 0  # 没有加分项

    def test_github_high_stars(self):
        item = NormalizedItem(
            source="github", source_type="github_repo",
            title="popular-repo", url="https://github.com/u/popular",
            raw={"stars": 15000, "has_readme": True, "latest_release": {"tag": "v1"}},
        )
        score = ScoringService.score(item)
        # stars > 10000: +20, has_readme: +10, has_release: +5
        assert score >= 35

    def test_github_medium_stars_with_keywords(self):
        item = NormalizedItem(
            source="github", source_type="github_repo",
            title="Awesome LLM Agent", url="https://github.com/u/agent",
            raw={"stars": 5000, "has_readme": True},
        )
        score = ScoringService.score(item)
        # stars > 1000: +10, has_readme: +10, keyword Agent: +10
        assert score >= 30

    def test_github_recent_update(self):
        item = NormalizedItem(
            source="github", source_type="github_repo",
            title="active-repo", url="https://github.com/u/active",
            raw={
                "stars": 500,
                "has_readme": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        score = ScoringService.score(item)
        # has_readme: +10, recent_update: +10
        assert score >= 20

    def test_aihot_daily_base(self):
        item = NormalizedItem(
            source="aihot", source_type="aihot_daily",
            title="Some AI news worth reading today",
            url="https://example.com",
            summary="A longer summary to avoid the short content penalty of 30 chars",
        )
        score = ScoringService.score(item)
        # daily: +15
        assert score >= 15

    def test_aihot_hot_keyword(self):
        item = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="OpenAI发布GPT-5，Agent能力大幅提升",
            url="https://example.com",
            summary="OpenAI released GPT-5 with major Agent improvements and tool use",
        )
        score = ScoringService.score(item)
        # keyword 'agent' and 'openai' both in title: +10
        assert score >= 10

    def test_aihot_today_published(self):
        item = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="Breaking AI News: latest developments in AI research papers",
            url="https://example.com",
            summary="A detailed summary to make the total content length exceed 30 chars threshold",
            published_at=datetime.now(timezone.utc).isoformat(),
        )
        score = ScoringService.score(item)
        # published today: +10
        assert score >= 10

    def test_aihot_short_content_penalty(self):
        """内容过短应扣分且被 clamp 到 0。"""
        item = NormalizedItem(
            source="aihot", source_type="aihot_news",
            title="Hi", url="https://example.com",
            summary="",  # total length < 30
        )
        score = ScoringService.score(item)
        # 标题+摘要 < 30: -5, clamp to 0
        assert score == 0

    def test_score_clamped(self):
        """分数应在 0-100 之间。"""
        item = NormalizedItem(
            source="github", source_type="github_repo",
            title="mega-repo", url="https://github.com/u/mega",
            raw={"stars": 50000, "has_readme": True, "latest_release": {"tag": "v2"}},
        )
        score = ScoringService.score(item)
        assert 0 <= score <= 100

    def test_score_all_sorts(self):
        items = [
            NormalizedItem(source="github", source_type="github_repo",
                           title="low", url="https://github.com/a/low",
                           raw={"stars": 10, "has_readme": False}),
            NormalizedItem(source="github", source_type="github_repo",
                           title="high", url="https://github.com/b/high",
                           raw={"stars": 20000, "has_readme": True, "latest_release": {"tag": "v1"}}),
        ]
        result = ScoringService.score_all(items)
        assert result[0].score >= result[1].score  # 按分数降序
