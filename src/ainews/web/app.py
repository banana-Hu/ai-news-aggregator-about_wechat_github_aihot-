"""
AI News Aggregator — Web 控制面板 (FastAPI)。
适配清新风格 SPA 前端。
"""

import json
import threading
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from jinja2 import Environment, FileSystemLoader

from ainews.core import TEMPLATES_DIR, read_lark_chat_id, ensure_user_config_dir
from ainews.services.source_fetch_service import fetch_sources, fetch_and_push
from ainews.services.push_service import push_ai_daily
from ainews.services.subscription_service import (
    get_followed, get_quality_recommendations, follow, unfollow, rate_article,
    get_article_ratings, get_creators_stats,
)

logger = logging.getLogger("ainews.web")

items_cache = []
log_history = []
lark_chat_id = read_lark_chat_id()

app = FastAPI(title="AI News Aggregator")
_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def add_log(msg: str, kind: str = "info"):
    t = datetime.now().strftime("%H:%M:%S")
    log_history.append({"time": t, "msg": msg, "kind": kind})
    if len(log_history) > 200:
        log_history[:50] = []


def render(name: str, **ctx) -> str:
    return _jinja_env.get_template(name).render(**ctx)


# ========== SPA 入口 ==========

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(render("base.html"))


# ========== API Routes ==========

@app.get("/api/status")
async def api_status():
    return JSONResponse({
        "items_count": len(items_cache),
        "log_count": len(log_history),
        "lark_configured": bool(lark_chat_id),
        "github_token": bool(open)
    })


@app.get("/api/logs")
async def api_logs():
    return JSONResponse(log_history[-100:])


@app.get("/api/items")
async def api_items():
    return JSONResponse([i.to_dict() for i in items_cache[-50:]])


@app.get("/api/followed")
async def api_followed():
    return JSONResponse(get_followed())


@app.get("/api/suggested")
async def api_suggested():
    return JSONResponse(get_quality_recommendations())


@app.get("/api/settings/state")
async def api_settings_state():
    return JSONResponse({
        "chat_id": read_lark_chat_id(),
        "github_token": bool(open),
    })


@app.post("/api/settings/lark")
async def save_lark(chat_id: str = Form("")):
    cid = chat_id.strip()
    if cid:
        d = ensure_user_config_dir()
        (d / ".env.lark").write_text(f"LARK_CHAT_ID={cid}\n", encoding="utf-8")
        global lark_chat_id
        lark_chat_id = cid
        add_log("飞书配置已保存", "ok")
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "msg": "群 ID 不能为空"})


@app.post("/api/fetch")
async def api_fetch(source: str = Form("all")):
    def task():
        src_map = {"aihot": ["aihot"], "wechat_mp": ["wechat_mp"], "github": ["github"], "all": None}
        add_log(f"开始抓取: {source}", "info")
        try:
            global items_cache
            items = fetch_sources(sources=src_map.get(source), log_func=add_log)
            if items:
                items_cache = items
            add_log(f"完成: {len(items)} 条", "ok")
        except Exception as e:
            add_log(f"抓取异常: {e}", "err")
    threading.Thread(target=task, daemon=True).start()
    return JSONResponse({"ok": True})


@app.post("/api/push")
async def api_push():
    if not items_cache:
        return JSONResponse({"ok": False, "msg": "没有数据"})
    cid = read_lark_chat_id()
    if not cid:
        return JSONResponse({"ok": False, "msg": "未配置飞书群 ID"})
    def task():
        ok = push_ai_daily(items_cache, chat_id=cid, chat_name=None)
        add_log("推送成功 ✅" if ok else "推送失败 ❌", "ok" if ok else "err")
    threading.Thread(target=task, daemon=True).start()
    return JSONResponse({"ok": True})


@app.post("/api/subscribe")
async def api_subscribe(creator_id: str = Form("")):
    follow(creator_id)
    return JSONResponse({"ok": True})


@app.post("/api/unsubscribe")
async def api_unsubscribe(creator_id: str = Form("")):
    unfollow(creator_id)
    return JSONResponse({"ok": True})


@app.post("/api/rate")
async def api_rate(url: str = Form(""), rating: int = Form(0)):
    if not url or rating < 1 or rating > 5:
        return JSONResponse({"ok": False})
    rate_article(url, rating)
    return JSONResponse({"ok": True})


@app.get("/api/ratings")
async def api_ratings(creator_id: str = ""):
    if not creator_id:
        return JSONResponse([])
    return JSONResponse(get_article_ratings(creator_id))


def run_server(host: str = "0.0.0.0", port: int = 8101):
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"Web 控制面板: http://localhost:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
