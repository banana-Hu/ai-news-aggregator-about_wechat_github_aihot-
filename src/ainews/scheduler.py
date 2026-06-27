"""
定时调度器：每日自动抓取 AI 资讯并推送飞书。

用法：
    python -m ainews.scheduler          # 立即执行一次
    python -m ainews.scheduler --loop   # 持续运行，每天 08:30 触发
"""

import time
import logging
import threading
from datetime import datetime, timezone, time as dtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ainews.scheduler")


def run_daily(fetch_github: bool = False):
    """执行一次完整的日报抓取 + 推送。"""
    from ainews.services.source_fetch_service import fetch_sources
    from ainews.services.push_service import push_ai_daily
    from ainews.core import read_lark_chat_id

    logger.info("=" * 50)
    logger.info("⏰ 启动每日定时抓取")
    logger.info("=" * 50)

    sources = ["aihot", "wechat_mp"]
    if fetch_github:
        sources.append("github")

    chat_id = read_lark_chat_id()
    logger.info(f"数据源: {sources}")
    logger.info(f"飞书群: {'已配置' if chat_id else '未配置'}")

    try:
        items = fetch_sources(sources=sources)
        logger.info(f"抓取完成: {len(items)} 条")

        if items and chat_id:
            logger.info("正在推送飞书...")
            ok = push_ai_daily(items, chat_id=chat_id, chat_name=None)
            logger.info("推送成功 ✅" if ok else "推送失败 ❌")
        elif not chat_id:
            logger.warning("未配置飞书群，跳过推送")
        else:
            logger.warning("无数据")
    except Exception as e:
        logger.error(f"每日任务异常: {e}", exc_info=True)

    logger.info("每日任务结束")


def loop_forever(target_hour: int = 8, target_minute: int = 30):
    """持续运行，每天到指定时间触发一次。"""
    logger.info(f"调度器启动: 每天 {target_hour:02d}:{target_minute:02d} 触发")

    last_run_date = None

    while True:
        now = datetime.now()
        today = now.date()

        # 计算下次触发时间
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        if target <= now:
            target = target.replace(day=today.day + 1) if today.month <= 12 else target

        wait_seconds = (target - now).total_seconds()
        logger.info(f"下次触发: {target.strftime('%Y-%m-%d %H:%M')} (等待 {wait_seconds/3600:.1f} 小时)")

        time.sleep(min(wait_seconds, 86400))  # 最多等一天

        new_now = datetime.now()
        if new_now.date() != last_run_date and new_now.hour >= target_hour:
            run_daily()
            last_run_date = new_now.date()
            time.sleep(60)  # 避免同一分钟内重复触发


if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        loop_forever()
    else:
        run_daily()
