# -*- coding: utf-8 -*-
"""
Subscription service: creator discovery, quality scoring, user follow/unfollow, article rating.
No auto-follow. Quality = system_avg_score + user_avg_rating * 10.
"""

import logging
from datetime import datetime, timezone

from ainews.models import get_connection, make_creator_id
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

RECOMMEND_MIN_SCORE = 8
RECOMMEND_MIN_ARTICLES = 2


def record_articles(items: list[NormalizedItem]) -> dict:
    """Record articles and creators from fetch results into the database.

    Does NOT auto-follow anyone. Just accumulates quality data.

    Returns: {recorded: int, new_creators: int}
    """
    conn = get_connection()
    stats = {"recorded": 0, "new_creators": 0}
    now = datetime.now(timezone.utc).isoformat()

    for item in items:
        if not item.author or not item.url:
            continue
        cid = make_creator_id(item.source, item.author)
        exists = conn.execute("SELECT id FROM creators WHERE id=?", (cid,)).fetchone()
        if exists:
            conn.execute(
                "UPDATE creators SET last_seen_at=?, article_count=article_count+1 WHERE id=?",
                (now, cid),
            )
        else:
            conn.execute(
                "INSERT INTO creators (id, name, source, first_seen_at, last_seen_at, article_count) VALUES (?,?,?,?,?,1)",
                (cid, item.author, item.source, now, now),
            )
            stats["new_creators"] += 1
        conn.execute(
            "INSERT OR IGNORE INTO articles_seen (url, creator_id, title, score, seen_at) VALUES (?,?,?,?,?)",
            (item.url, cid, item.title, item.score, now),
        )
        stats["recorded"] += 1

    conn.commit()
    conn.execute("""
        UPDATE creators SET quality_score = COALESCE(
            (SELECT AVG(score) FROM articles_seen WHERE creator_id=creators.id AND score > 0), 0)
        + COALESCE(
            (SELECT AVG(user_rating) * 10 FROM articles_seen WHERE creator_id=creators.id AND user_rating IS NOT NULL), 0)
    """)
    conn.commit()
    conn.close()
    logger.info(f"Recorded {stats['recorded']} articles, {stats['new_creators']} new creators")
    return stats


def get_quality_recommendations(limit: int = 10) -> list[dict]:
    """Recommend high-quality unfollowed creators based on quality scores."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT c.*,
               (SELECT AVG(score) FROM articles_seen WHERE creator_id=c.id AND score>0) as sys_avg,
               (SELECT AVG(user_rating) FROM articles_seen WHERE creator_id=c.id AND user_rating IS NOT NULL) as user_avg,
               (SELECT COUNT(*) FROM articles_seen WHERE creator_id=c.id) as total_articles,
               (SELECT COUNT(*) FROM articles_seen WHERE creator_id=c.id AND user_rating IS NOT NULL) as rated_articles
        FROM creators c
        WHERE c.article_count >= ? AND c.quality_score >= ? AND c.is_followed = 0
        ORDER BY c.quality_score DESC
        LIMIT ?
    """, (RECOMMEND_MIN_ARTICLES, RECOMMEND_MIN_SCORE, limit)).fetchall()
    conn.close()
    return [_enrich_reason(dict(r)) for r in cursor]


def _enrich_reason(d: dict) -> dict:
    parts = []
    if d.get("user_avg") and d["user_avg"] >= 4:
        parts.append("User rated {:.1f}/5".format(d["user_avg"]))
    elif d.get("sys_avg") and d["sys_avg"] >= 80:
        parts.append("System score {:.0f}".format(d["sys_avg"]))
    if d.get("total_articles", 0) >= 5:
        parts.append("{} articles".format(d["total_articles"]))
    if not parts:
        parts.append("Quality content")
    d["reason"] = ", ".join(parts)
    return d


def get_followed() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, (SELECT COUNT(*) FROM articles_seen WHERE creator_id=c.id AND user_rating IS NOT NULL) as rated_count
        FROM creators c WHERE c.is_followed = 1
        ORDER BY c.quality_score DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def follow(creator_id: str):
    conn = get_connection()
    conn.execute("UPDATE creators SET is_followed=1, auto_followed=0 WHERE id=?", (creator_id,))
    conn.commit(); conn.close()
    logger.info(f"Followed: {creator_id}")


def unfollow(creator_id: str):
    conn = get_connection()
    conn.execute("UPDATE creators SET is_followed=0, auto_followed=0 WHERE id=?", (creator_id,))
    conn.commit(); conn.close()
    logger.info(f"Unfollowed: {creator_id}")


def rate_article(url: str, rating: int):
    if not 1 <= rating <= 5:
        raise ValueError("Rating must be 1-5")
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("UPDATE articles_seen SET user_rating=?, rated_at=? WHERE url=?", (rating, now, url))
    conn.execute("""
        UPDATE creators SET quality_score = COALESCE(
            (SELECT AVG(score) FROM articles_seen WHERE creator_id=creators.id AND score > 0), 0)
        + COALESCE(
            (SELECT AVG(user_rating) * 10 FROM articles_seen WHERE creator_id=creators.id AND user_rating IS NOT NULL), 0)
        WHERE id = (SELECT creator_id FROM articles_seen WHERE url=?)
    """, (url,))
    conn.commit(); conn.close()


def get_article_ratings(creator_id: str, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles_seen WHERE creator_id=? ORDER BY seen_at DESC LIMIT ?",
        (creator_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_creators_stats() -> dict:
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    followed = conn.execute("SELECT COUNT(*) FROM creators WHERE is_followed=1").fetchone()[0]
    recommend = conn.execute(
        "SELECT COUNT(*) FROM creators WHERE is_followed=0 AND quality_score >= ?",
        (RECOMMEND_MIN_SCORE,),
    ).fetchone()[0]
    conn.close()
    return {"total": total, "followed": followed, "recommendable": recommend}
