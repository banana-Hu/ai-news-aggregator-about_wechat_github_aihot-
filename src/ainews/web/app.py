"""
AI News Aggregator — Web 控制面板 (FastAPI)。
"""

import os
import sys
import json
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ainews.connectors.aihot_connector import AIHOTConnector
from ainews.connectors.github_connector import GitHubConnector
from ainews.connectors.wechat_mp_connector import WeChatMpConnector
from ainews.services.dedup_service import DedupService
from ainews.services.scoring_service import ScoringService
from ainews.services.push_service import push_ai_daily

logger = logging.getLogger("ainews.web")

# 全局状态
items_cache = []
log_history = []

app = FastAPI(title="AI News Aggregator")

here = Path(__file__).parent
_jinja_env = Environment(
    loader=FileSystemLoader(str(here / "templates")),
    autoescape=select_autoescape(["html"]),
)


def render(name: str, **context) -> str:
    """渲染 Jinja2 模板。"""
    tpl = _jinja_env.get_template(name)
    return tpl.render(**context)


def add_log(msg: str, kind: str = "info"):
    time_str = datetime.now().strftime("%H:%M:%S")
    log_history.append({"time": time_str, "msg": msg, "kind": kind})
    if len(log_history) > 200:
        log_history[:50] = []


def load_lark_chat_id() -> str:
    for p in [str(here.parent.parent.parent / ".env.lark"),
              os.path.join(os.path.expanduser("~"), ".ainews", ".env.lark")]:
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("LARK_CHAT_ID="):
                        return line.split("=", 1)[1].strip()
    return ""


# ========== API Routes ==========

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return HTMLResponse(render("dashboard.html",
        current_page="/",
        items_count=len(items_cache),
        log_count=len(log_history),
        lark_configured=bool(load_lark_chat_id()),
        recent_logs=log_history[-10:],
    ))


@app.get("/fetch", response_class=HTMLResponse)
async def fetch_page(request: Request):
    return HTMLResponse(render("fetch.html",
        current_page="/fetch",
        logs=log_history[-50:],
    ))


@app.get("/push", response_class=HTMLResponse)
async def push_page(request: Request):
    chat_id = load_lark_chat_id()
    return HTMLResponse(render("push.html",
        current_page="/push",
        items_count=len(items_cache),
        lark_configured=bool(chat_id),
        chat_id=chat_id,
        logs=log_history[-30:],
    ))


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    chat_id = load_lark_chat_id()
    return HTMLResponse(render("settings.html",
        current_page="/settings",
        chat_id=chat_id,
        github_token=bool(os.environ.get("GITHUB_TOKEN")),
    ))


@app.get("/api/logs")
async def api_logs():
    return JSONResponse(log_history[-100:])


@app.get("/api/items")
async def api_items():
    return JSONResponse([i.to_dict() for i in items_cache[-50:]])


@app.post("/api/fetch")
async def api_fetch(source: str = Form("all")):
    def task():
        global items_cache
        add_log(f"开始抓取: {source}", "info")
        fetched = []
        try:
            if source in ("all", "aihot"):
                items = AIHOTConnector({"max_items": 30}).safe_fetch()
                add_log(f"AIHOT: {len(items)} 条", "ok")
                fetched.extend(items)
            if source in ("all", "wechat_mp"):
                items = WeChatMpConnector({"extract_content": False, "max_articles": 10}).safe_fetch()
                add_log(f"公众号: {len(items)} 条", "ok")
                fetched.extend(items)
            if source in ("all", "github"):
                items = GitHubConnector({}).safe_fetch()
                add_log(f"GitHub: {len(items)} 条", "ok")
                fetched.extend(items)

            if fetched:
                dedup = DedupService()
                fetched = dedup.deduplicate(fetched)
                fetched = ScoringService.score_all(fetched)
                items_cache = fetched
                add_log(f"共 {len(fetched)} 条（去重评分后）", "ok")
            else:
                add_log("未获取到数据", "warn")
        except Exception as e:
            add_log(f"抓取异常: {e}", "err")

    threading.Thread(target=task, daemon=True).start()
    return JSONResponse({"ok": True, "msg": "抓取任务已启动"})


@app.post("/api/push")
async def api_push():
    if not items_cache:
        return JSONResponse({"ok": False, "msg": "没有数据，请先抓取"})
    chat_id = load_lark_chat_id()
    if not chat_id:
        return JSONResponse({"ok": False, "msg": "未配置飞书群 ID"})

    def task():
        try:
            add_log(f"推送 {len(items_cache)} 条到飞书...", "info")
            ok = push_ai_daily(items_cache, chat_id=chat_id, chat_name=None)
            add_log("推送成功 ✅" if ok else "推送失败 ❌", "ok" if ok else "err")
        except Exception as e:
            add_log(f"推送异常: {e}", "err")

    threading.Thread(target=task, daemon=True).start()
    return JSONResponse({"ok": True, "msg": "推送任务已启动"})


@app.post("/api/settings/lark")
async def save_lark(chat_id: str = Form("")):
    cid = chat_id.strip()
    if cid:
        d = os.path.join(os.path.expanduser("~"), ".ainews")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, ".env.lark"), "w") as f:
            f.write(f"LARK_CHAT_ID={cid}\n")
        add_log("飞书配置已保存", "ok")
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "msg": "群 ID 不能为空"})


def run_server(host: str = "0.0.0.0", port: int = 8099):
    """启动 Web 控制面板。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"Web 控制面板: http://localhost:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
