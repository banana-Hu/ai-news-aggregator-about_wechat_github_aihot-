"""
订阅服务：创作者发现、自动关注、用户订阅管理、文章评分。
"""

import logging
from datetime import datetime, timezone
from collections import Counter

from ainews.models import get_connection, make_creator_id
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# 自动关注阈值
AUTO_FOLLOW_MIN_ARTICLES = 5        # 最少出现文章数
AUTO_FOLLOW_MIN_AVG_SCORE = 75      # 平均评分阈值


def auto_discover(items: list[NormalizedItem]) -> dict:
    """从抓取结果自动发现创作者，注册到数据库。

    Returns:
        {new: int, updated: int, auto_followed: int}
    """
    conn = get_connection()
    stats = {"new": 0, "updated": 0, "auto_followed": 0}

    for item in items:
        if not item.author:
            continue

        cid = make_creator_id(item.source, item.author)
        now = datetime.now(timezone.utc).isoformat()

        # 注册创作者
        existing = conn.execute("SELECT id FROM creators WHERE id=?", (cid,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE creators SET last_seen_at=?, article_count=article_count+1 WHERE id=?",
                (now, cid),
            )
            stats["updated"] += 1
        else:
            conn.execute(
                "INSERT INTO creators (id, name, source, first_seen_at, last_seen_at, article_count) VALUES (?,?,?,?,?,1)",
                (cid, item.author, item.source, now, now),
            )
            stats["new"] += 1

        # 记录文章
        conn.execute(
            "INSERT OR IGNORE INTO articles_seen (url, creator_id, title, score, seen_at) VALUES (?,?,?,?,?)",
            (item.url, cid, item.title, item.score, now),
        )

    conn.commit()

    # 自动关注：达到阈值的创作者
    cursor = conn.execute("""
        SELECT id, quality_score FROM creators
        WHERE is_followed=1 AND auto_followed=0 AND article_count >= ?
    """, (AUTO_FOLLOW_MIN_ARTICLES,))

    for row in cursor:
        # 计算平均评分
        avg = conn.execute(
            "SELECT AVG(score) FROM articles_seen WHERE creator_id=? AND score > 0",
            (row["id"],),
        ).fetchone()[0] or 0

        if avg >= AUTO_FOLLOW_MIN_AVG_SCORE:
            conn.execute(
                "UPDATE creators SET auto_followed=1, quality_score=? WHERE id=?",
                (avg, row["id"]),
            )
            stats["auto_followed"] += 1

    conn.commit()
    conn.close()

    if stats["auto_followed"]:
        logger.info(f"自动关注了 {stats['auto_followed']} 个高质量创作者")
    return stats


def get_followed() -> list[dict]:
    """获取当前关注的创作者列表。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM creators WHERE is_followed=1 ORDER BY quality_score DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_suggested(limit: int = 10) -> list[dict]:
    """获取推荐关注的创作者（高频出现但未关注）。"""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM creators
           WHERE is_followed=0 AND article_count >= 3
           ORDER BY quality_score DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def follow(creator_id: str, auto: bool = False):
    """关注创作者。"""
    conn = get_connection()
    conn.execute(
        "UPDATE creators SET is_followed=1, auto_followed=? WHERE id=?",
        (1 if auto else 0, creator_id),
    )
    conn.commit()
    conn.close()


def unfollow(creator_id: str):
    """取关创作者。"""
    conn = get_connection()
    conn.execute(
        "UPDATE creators SET is_followed=0, auto_followed=0 WHERE id=?",
        (creator_id,),
    )
    conn.commit()
    conn.close()


def rate_article(url: str, rating: int):
    """用户给文章评分 (1-5)。"""
    if not 1 <= rating <= 5:
        raise ValueError("评分范围 1-5")
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE articles_seen SET user_rating=?, rated_at=? WHERE url=?",
        (rating, now, url),
    )
    # 更新创作者的 quality_score
    conn.execute("""
        UPDATE creators SET quality_score = COALESCE(
            (SELECT AVG(user_rating) * 20 FROM articles_seen
             WHERE creator_id=creators.id AND user_rating IS NOT NULL), quality_score)
        WHERE id = (SELECT creator_id FROM articles_seen WHERE url=?)
    """, (url,))
    conn.commit()
    conn.close()


def get_article_ratings(creator_id: str, limit: int = 20) -> list[dict]:
    """获取创作者的文章评分列表。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM articles_seen WHERE creator_id=? ORDER BY seen_at DESC LIMIT ?",
        (creator_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_creators_stats() -> dict:
    """创作者统计概览。"""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM creators").fetchone()[0]
    followed = conn.execute("SELECT COUNT(*) FROM creators WHERE is_followed=1").fetchone()[0]
    auto = conn.execute("SELECT COUNT(*) FROM creators WHERE auto_followed=1").fetchone()[0]
    conn.close()
    return {"total": total, "followed": followed, "auto_followed": auto}
