"""
AI News Aggregator 入口。

启动桌面控制台:
    python -m ainews
    ainews

命令行模式:
    python -m ainews fetch
    python -m ainews push
"""

import sys
import argparse


def main():
    """主入口。"""
    if len(sys.argv) > 1:
        cli_main()
    else:
        # 默认启动桌面控制台
        from ainews.ui.app import main as desktop_main
        desktop_main()


def cli_main():
    """CLI 子命令入口。"""
    parser = argparse.ArgumentParser(description="AI News Aggregator")
    sub = parser.add_subparsers(dest="command")

    # fetch
    fetch_p = sub.add_parser("fetch", help="抓取数据源")
    fetch_p.add_argument("--source", "-s", choices=["all", "aihot", "github", "wechat_mp"],
                         default="all")
    fetch_p.add_argument("--limit", "-l", type=int, default=0)
    fetch_p.add_argument("--output", "-o", default="")
    fetch_p.add_argument("--print", "-p", action="store_true")

    # push
    push_p = sub.add_parser("push", help="抓取并推送飞书")
    push_p.add_argument("--source", "-s", choices=["all", "aihot", "github", "wechat_mp"],
                        default="all")
    push_p.add_argument("--chat-id", type=str, default="")
    push_p.add_argument("--dry-run", action="store_true")

    # web
    web_p = sub.add_parser("web", help="启动 Web 控制面板")
    web_p.add_argument("--host", type=str, default="0.0.0.0")
    web_p.add_argument("--port", "-p", type=int, default=8099)

    args = parser.parse_args()

    if args.command == "fetch":
        _cmd_fetch(args)
    elif args.command == "push":
        _cmd_push(args)
    elif args.command == "web":
        _cmd_web(args)
    else:
        parser.print_help()


def _cmd_web(args):
    from ainews.web.app import run_server
    run_server(host=args.host, port=args.port)


def _cmd_fetch(args):
    from ainews.services.source_fetch_service import fetch_external_ai_sources
    import json

    config = {}
    if args.source == "aihot":
        config["github"] = {"queries": []}
        config["wechat_mp"] = {"enabled": False}
    elif args.source == "github":
        config["aihot"] = {"max_items": 0}
        config["wechat_mp"] = {"enabled": False}
    elif args.source == "wechat_mp":
        config["github"] = {"queries": []}
        config["aihot"] = {"max_items": 0}

    items = fetch_external_ai_sources(config=config, verbose=False)
    if args.limit > 0:
        items = items[:args.limit]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump([i.to_dict() for i in items], f, ensure_ascii=False, indent=2)
        print(f"已保存 {len(items)} 条到 {args.output}")
    elif args.print:
        for i, item in enumerate(items[:20], 1):
            print(f"{i}. [{item.source}] {item.title}")
            print(f"   {item.url}")
    else:
        print(f"共 {len(items)} 条")


def _cmd_push(args):
    from ainews.services.source_fetch_service import fetch_external_ai_sources
    from ainews.services.push_service import push_ai_daily
    import os

    config = {}
    if args.source == "aihot":
        config["github"] = {"queries": []}
        config["wechat_mp"] = {"enabled": False}
    elif args.source == "wechat_mp":
        config["github"] = {"queries": []}
        config["aihot"] = {"max_items": 0}

    chat_id = args.chat_id
    if not chat_id:
        from ainews.core import LARK_ENV_PATH, USER_LARK_ENV_PATH
        env_path = LARK_ENV_PATH if LARK_ENV_PATH.exists() else USER_LARK_ENV_PATH
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith("LARK_CHAT_ID="):
                        chat_id = line.split("=", 1)[1].strip()

    items = fetch_external_ai_sources(config=config, verbose=False)
    if items and chat_id:
        ok = push_ai_daily(items, chat_id=chat_id, chat_name=None, dry_run=args.dry_run)
        print("✅ 推送成功" if ok else "❌ 推送失败")
    elif not chat_id:
        print("❌ 未配置飞书群 ID")
    else:
        print("❌ 无数据")


if __name__ == "__main__":
    main()
