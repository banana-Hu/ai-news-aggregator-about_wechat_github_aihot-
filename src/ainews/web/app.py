"""
AI News Aggregator — Web 控制面板 (FastAPI)。
"""

import os
import sys
import json
import threading
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ainews.core import TEMPLATES_DIR, read_lark_chat_id, ensure_user_config_dir
from ainews.services.source_fetch_service import fetch_sources, fetch_and_push
from ainews.services.push_service import push_ai_daily
from ainews.services.subscription_service import (
    get_followed, get_quality_recommendations, follow, unfollow, rate_article,
    get_article_ratings, get_creators_stats,
)

logger = logging.getLogger("ainews.web")

# 全局状态
items_cache = []
log_history = []

from pathlib import Path

app = FastAPI(title="AI News Aggregator")

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
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


load_lark_chat_id = read_lark_chat_id  # 统一路径


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


# ========== 订阅管理 ==========

@app.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request):
    stats = get_creators_stats()
    followed = get_followed()
    recommended = get_quality_recommendations()
    return HTMLResponse(render("subscriptions.html",
        current_page="/subscriptions",
        stats=stats,
        followed=followed,
        recommended=recommended,
    ))


@app.post("/api/subscribe")
async def api_subscribe(creator_id: str = Form("")):
    if not creator_id:
        return JSONResponse({"ok": False, "msg": "缺少 creator_id"})
    follow(creator_id)
    return JSONResponse({"ok": True})


@app.post("/api/unsubscribe")
async def api_unsubscribe(creator_id: str = Form("")):
    if not creator_id:
        return JSONResponse({"ok": False, "msg": "缺少 creator_id"})
    unfollow(creator_id)
    return JSONResponse({"ok": True})


@app.post("/api/rate")
async def api_rate(url: str = Form(""), rating: int = Form(0)):
    if not url or rating < 1 or rating > 5:
        return JSONResponse({"ok": False, "msg": "参数错误"})
    rate_article(url, rating)
    add_log(f"评分: {url[:50]}... → {rating} 星", "ok")
    return JSONResponse({"ok": True})


@app.get("/api/ratings")
async def api_ratings(creator_id: str = ""):
    if not creator_id:
        return JSONResponse([])
    ratings = get_article_ratings(creator_id)
    return JSONResponse(ratings)


# ========== API Routes ==========

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
        src_map = {"aihot": ["aihot"], "wechat_mp": ["wechat_mp"], "github": ["github"], "all": None}
        try:
            items = fetch_sources(sources=src_map.get(source), log_func=add_log)
            if items:
                items_cache = items
                add_log(f"共 {len(items)} 条", "ok")
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
