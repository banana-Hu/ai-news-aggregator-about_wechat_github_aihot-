"""
飞书推送服务。
将 AI 日报内容格式化为飞书 post 富文本（原生格式，链接可点击）。
"""

import json
import logging
import subprocess
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

SUMMARY_MAX_LEN = 120
MAX_ITEMS_PER_SECTION = 10


def _lark_cli() -> str:
    cli_env = os.environ.get("LARK_CLI_PATH")
    if cli_env:
        return cli_env
    return "lark-cli.cmd" if sys.platform == "win32" else "lark-cli"


def _sanitize_for_cmd(text: str) -> str:
    """替换 cmd.exe 特殊字符，避免被解释为管道/重定向。"""
    return text.replace("|", "│").replace(">", "＞").replace("<", "＜")


def _run_lark(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """执行 lark-cli 命令，兼容 Windows .cmd 和编码。"""
    # 清除 Agent 环境变量，避免 lark-cli 绑定冲突
    env = os.environ.copy()
    for var in ("HERMES_HOME", "OPENCLAW_HOME", "REASONIX_HOME", "CODEBUDDY_HOME"):
        env.pop(var, None)

    if sys.platform == "win32":
        args = [_sanitize_for_cmd(a) if "|" in a or ">" in a or "<" in a else a for a in args]
        cmd_str = subprocess.list2cmdline(args)
        result = subprocess.run(
            cmd_str, shell=True, capture_output=True, timeout=timeout, env=env,
        )
    else:
        result = subprocess.run(
            args, capture_output=True, timeout=timeout, text=True, env=env,
        )
    return result


def _decode_output(r: subprocess.CompletedProcess) -> tuple[int, str, str]:
    """解码子进程输出，兼容 Windows GBK。"""
    rc = r.returncode
    if r.stdout and isinstance(r.stdout, bytes):
        out = r.stdout.decode("gbk", errors="replace")
    else:
        out = r.stdout or ""
    if r.stderr and isinstance(r.stderr, bytes):
        err = r.stderr.decode("gbk", errors="replace")
    else:
        err = r.stderr or ""
    return rc, out.strip(), err.strip()


def _t(text: str) -> dict:
    """飞书 post 文本块。"""
    return {"tag": "text", "text": text}


def _a(text: str, href: str) -> dict:
    """飞书 post 链接块。"""
    return {"tag": "a", "text": text, "href": href}


def _empty() -> dict:
    """飞书 post 空行。"""
    return {"tag": "text", "text": ""}


def build_post_content(items: list[NormalizedItem]) -> dict:
    """构建飞书 post 消息内容。

    返回可以直接序列化为 JSON 的 content 结构。
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = []

    # 标题
    content.append([_t(f"🤖 AI 情报日报 · {today}")])
    content.append([_t(f"共 {len(items)} 条内容")])
    content.append([_t("")])
    content.append([_t("━━━━━━━━━━━━━━━━━━")])
    content.append([_t("")])

    # ---- AIHOT 资讯 ----
    aihot_items = [i for i in items if i.source == "aihot"]
    if aihot_items:
        content.append([_t(f"🔥 AI 资讯精选（{len(aihot_items)} 条）")])
        content.append([_t("──────────────────────────")])
        for i, item in enumerate(aihot_items[:MAX_ITEMS_PER_SECTION], 1):
            content.append([_t(f"{i}. {item.title}")])
            source_info = ""
            if item.author:
                source_info = f"来源: {item.author}  |  评分: {item.score}"
                content.append([_t(f"  {source_info}")])
            if item.summary:
                summary = item.summary[:SUMMARY_MAX_LEN]
                if len(item.summary) > SUMMARY_MAX_LEN:
                    summary += "…"
                content.append([_t(f"  {summary}")])
            content.append([_a("  查看原文 →", item.url)])
            if item.tags:
                content.append([_t(f"  标签: {' '.join(item.tags[:4])}")])
            content.append([_empty()])

    # ---- GitHub 项目 ----
    github_items = [i for i in items if i.source == "github"]
    if github_items:
        content.append([_t(f"📦 GitHub 热门项目（{len(github_items)} 个）")])
        content.append([_t("──────────────────────────")])
        for i, item in enumerate(github_items[:MAX_ITEMS_PER_SECTION], 1):
            content.append([_t(f"{i}. {item.title}")])
            stars = item.raw.get("stars", 0) if item.raw else 0
            lang = item.raw.get("language", "") if item.raw else ""
            parts = []
            if stars:
                parts.append(f"Stars: {stars}")
            if lang:
                parts.append(f"Lang: {lang}")
            if parts:
                content.append([_t(f"  {' | '.join(parts)}")])
            if item.summary:
                content.append([_t(f"  {item.summary[:100]}")])
            content.append([_a("  查看项目 →", item.url)])
            content.append([_empty()])

    # ---- 公众号文章 ----
    mp_items = [i for i in items if i.source == "wechat_mp"]
    if mp_items:
        content.append([_t(f"📢 公众号文章精选（{len(mp_items)} 条）")])
        content.append([_t("──────────────────────────")])
        for i, item in enumerate(mp_items[:MAX_ITEMS_PER_SECTION], 1):
            content.append([_t(f"{i}. {item.title}")])
            if item.author:
                content.append([_t(f"  来源: {item.author}")])
            content.append([_a("  阅读全文 →", item.url)])
            content.append([_empty()])

    # ---- 统计 ----
    content.append([_t("━━━━━━━━━━━━━━━━━━")])
    sources = {}
    for item in items:
        sources[item.source] = sources.get(item.source, 0) + 1
    for src, count in sources.items():
        content.append([_t(f"{src}: {count} 条")])
    content.append([_empty()])

    fetched_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content.append([_t(f"抓取时间: {fetched_time}")])

    return {
        "zh_cn": {
            "title": f"AI 情报日报 · {today}",
            "content": content,
        }
    }


def find_chat_id(chat_name: str) -> Optional[str]:
    try:
        cli = _lark_cli()
        result = _run_lark(
            [cli, "im", "+chat-search", "--query", chat_name, "--format", "json"],
            timeout=15,
        )
        rc, out, err = _decode_output(result)
        if rc != 0:
            logger.error(f"搜索群聊失败: {err[:200]}")
            return None
        data = json.loads(out)
        if isinstance(data, list) and len(data) > 0:
            return data[0].get("chat_id")
        elif isinstance(data, dict):
            items = data.get("items", data.get("data", []))
            if isinstance(items, list) and len(items) > 0:
                return items[0].get("chat_id")
        return None
    except Exception as e:
        logger.error(f"搜索群聊异常: {e}")
        return None


def push_to_lark(
    content: str,
    chat_id: Optional[str] = None,
    chat_name: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """推送 post 富文本消息到飞书群。

    Args:
        content: JSON 字符串（post 格式）
        chat_id: 目标群 ID
        chat_name: 群名称
        dry_run: 仅打印

    Returns:
        是否成功
    """
    if chat_id and chat_name:
        logger.warning("同时指定了 chat_id 和 chat_name，优先使用 chat_id")

    if not chat_id and chat_name:
        logger.info(f"通过群名称搜索: {chat_name}")
        chat_id = find_chat_id(chat_name)
        if not chat_id:
            logger.error(f"未找到群: {chat_name}")
            return False

    if not chat_id:
        logger.error("未指定目标群")
        return False

    cli = _lark_cli()
    cmd = [
        cli, "im", "+messages-send",
        "--chat-id", chat_id,
        "--msg-type", "post",
        "--content", content,
        "--format", "json",
    ]

    if dry_run:
        logger.info(f"[DRY RUN] 将发送到群 {chat_id}")
        print(content[:1000])
        return True

    try:
        logger.info(f"推送日报到飞书群 {chat_id}...")
        result = _run_lark(cmd, timeout=30)
        rc, out, err = _decode_output(result)
        if rc == 0:
            logger.info("推送成功")
            return True
        else:
            logger.error(f"推送失败: {err[:300] or out[:300]}")
            return False
    except subprocess.TimeoutExpired:
        logger.error("推送超时")
        return False
    except Exception as e:
        logger.error(f"推送异常: {e}")
        return False


def push_ai_daily(
    items: list[NormalizedItem],
    chat_id: Optional[str] = None,
    chat_name: Optional[str] = None,
    dry_run: bool = False,
    title: Optional[str] = None,
) -> bool:
    """一键推送 AI 日报（post 富文本格式）。"""
    post = build_post_content(items)
    content_json = json.dumps(post, ensure_ascii=False)
    if title:
        post["zh_cn"]["title"] = title
        content_json = json.dumps(post, ensure_ascii=False)
    return push_to_lark(content_json, chat_id=chat_id, chat_name=chat_name, dry_run=dry_run)
