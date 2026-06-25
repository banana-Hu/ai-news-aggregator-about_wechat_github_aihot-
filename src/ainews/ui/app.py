"""AI News Aggregator 桌面控制台 — Flet UI。"""

import json
import threading
from datetime import datetime, timezone

import flet as ft

from ainews.core import read_lark_chat_id, ensure_user_config_dir
from ainews.services.source_fetch_service import fetch_and_push, fetch_sources
from ainews.services.push_service import push_ai_daily


class AIAggregatorApp:
    """桌面控制台主程序。"""

    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "AI 情报聚合 · 控制台"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.width = 1100
        self.page.window.height = 750
        self.page.window.min_width = 800
        self.page.window.min_height = 600
        self.page.padding = 0
        self.page.spacing = 0

        # 状态变量
        self.items = []
        self.running = False
        self.status_text = ft.Text("就绪", size=13, color=ft.Colors.GREY_400)
        self.log_output = ft.ListView(expand=True, spacing=4, auto_scroll=True)
        self.lark_chat_id = self._load_lark_chat_id()

        # 构建 UI
        self._build_ui()

    def _load_lark_chat_id(self) -> str:
        return read_lark_chat_id()
                    for line in f:
                        line = line.strip()
                        if line.startswith("LARK_CHAT_ID="):
                            return line.split("=", 1)[1].strip()
        return ""

    def _log(self, msg: str, kind: str = "info"):
        """添加日志行。"""
        time_str = datetime.now().strftime("%H:%M:%S")
        colors = {"info": ft.Colors.BLUE_200, "ok": ft.Colors.GREEN_300,
                  "warn": ft.Colors.ORANGE_300, "err": ft.Colors.RED_300}
        color = colors.get(kind, ft.Colors.GREY_300)
        self.log_output.controls.append(
            ft.Row([
                ft.Text(time_str, size=11, color=ft.Colors.GREY_500, width=60),
                ft.Text(msg, size=12, color=color, selectable=True),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.START)
        )
        self.log_output.scroll_to(offset=-1, duration=300)
        self.page.update()

    def _set_busy(self, busy: bool):
        self.running = busy
        self.status_text.value = "运行中..." if busy else "就绪"
        self.status_text.color = ft.Colors.GREEN_300 if busy else ft.Colors.GREY_400
        self.page.update()

    # ========== 页面构建 ==========

    def _build_ui(self):
        """构建完整 UI。"""
        sidebar = self._build_sidebar()
        self.content_area = ft.Container(
            content=self._build_dashboard(),
            expand=True,
            padding=25,
            bgcolor=ft.Colors.GREY_900,
        )
        layout = ft.Row([sidebar, self.content_area], spacing=0, expand=True)
        self.page.add(layout)

    def _build_sidebar(self):
        """左侧导航栏。"""
        def nav_click(e):
            target = e.control.data
            pages = {
                "dashboard": self._build_dashboard,
                "fetch": self._build_fetch_page,
                "settings": self._build_settings_page,
            }
            if target in pages:
                self.content_area.content = pages[target]()
                self.content_area.update()

        nav_items = [
            ("📊", "概览", "dashboard"),
            ("📡", "数据抓取", "fetch"),
            ("⚙️", "设置", "settings"),
        ]

        controls = []
        for icon, label, key in nav_items:
            btn = ft.Container(
                content=ft.Row([
                    ft.Text(icon, size=16),
                    ft.Text(label, size=13),
                ], spacing=8),
                data=key,
                on_click=nav_click,
                padding=ft.padding.symmetric(vertical=10, horizontal=15),
                border_radius=8,
                ink=True,
            )
            controls.append(btn)

        return ft.Container(
            content=ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Text("🤖", size=28),
                        ft.Text("AI 情报", size=14, weight=ft.FontWeight.BOLD),
                        ft.Text("控制台", size=11, color=ft.Colors.GREY_400),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=20,
                ),
                ft.Divider(height=1, color=ft.Colors.GREY_700),
                *controls,
                ft.Container(expand=True),
                ft.Container(
                    content=self.status_text,
                    padding=15,
                ),
            ], spacing=2),
            width=150,
            bgcolor=ft.Colors.GREY_850,
            border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_700)),
        )

    # ========== 概览页 ==========

    def _build_dashboard(self):
        """概览仪表盘。"""
        stats = [
            ("AIHOT 资讯", "待抓取", ft.Colors.BLUE_300, "aihot"),
            ("GitHub 项目", "待抓取", ft.Colors.GREEN_300, "github"),
            ("公众号文章", "待抓取", ft.Colors.ORANGE_300, "wechat_mp"),
        ]
        cards = []
        for title, value, color, key in stats:
            cards.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(title, size=13, color=ft.Colors.GREY_300),
                        ft.Text(value, size=22, weight=ft.FontWeight.BOLD, color=color),
                    ]),
                    padding=20,
                    border_radius=12,
                    bgcolor=ft.Colors.GREY_850,
                    expand=True,
                    ink=False,
                )
            )

        lark_status = "已配置 ✅" if self.lark_chat_id else "未配置 ⚠️"
        return ft.Column([
            ft.Text("📊 控制台概览", size=20, weight=ft.FontWeight.BOLD),
            ft.Text("AI 情报聚合日报系统 · 桌面管理端", size=12, color=ft.Colors.GREY_400),
            ft.Container(height=20),
            ft.Row(cards, spacing=15),
            ft.Container(height=20),
            ft.Container(
                content=ft.Column([
                    ft.Text("快速操作", size=15, weight=ft.FontWeight.BOLD),
                    ft.Container(height=10),
                    ft.ElevatedButton("🚀 立即抓取全部数据源", icon=ft.Icons.PLAY_ARROW,
                                     on_click=lambda _: self._switch_to_fetch(),
                                     height=45),
                    ft.Container(height=8),
                    ft.Row([
                        ft.ElevatedButton("📤 抓取并推送飞书", icon=ft.Icons.SEND,
                                          on_click=lambda _: self._run_fetch_and_push()),
                        ft.ElevatedButton("📋 仅推送公众号链接", icon=ft.Icons.ARTICLE,
                                          on_click=lambda _: self._push_mp_only()),
                    ], spacing=10),
                ]),
                padding=20,
                border_radius=12,
                bgcolor=ft.Colors.GREY_850,
            ),
            ft.Container(height=12),
            ft.Container(
                content=ft.Row([
                    ft.Text(f"飞书推送: {lark_status}", size=12),
                    ft.Container(expand=True),
                    ft.Text(f"v0.1.0", size=11, color=ft.Colors.GREY_500),
                ]),
            ),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    def _switch_to_fetch(self):
        self.content_area.content = self._build_fetch_page()
        self.content_area.update()

    # ========== 数据抓取页 ==========

    def _build_fetch_page(self):
        """抓取控制页。"""
        self.log_output = ft.ListView(expand=True, spacing=4, auto_scroll=True)
        self.log_output.controls.append(
            ft.Text("📋 操作日志", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_300)
        )

        return ft.Column([
            ft.Text("📡 数据抓取控制", size=20, weight=ft.FontWeight.BOLD),
            ft.Text("选择数据源并触发抓取，结果可推送飞书", size=12, color=ft.Colors.GREY_400),
            ft.Container(height=15),
            ft.Row([
                ft.ElevatedButton("📥 抓取全部数据源", icon=ft.Icons.DOWNLOAD,
                                  on_click=lambda _: threading.Thread(target=self._run_fetch_all, daemon=True).start()),
                ft.ElevatedButton("🔥 仅 AIHOT", on_click=lambda _: threading.Thread(target=self._run_fetch, args=("aihot",), daemon=True).start()),
                ft.ElevatedButton("🐙 仅 GitHub", on_click=lambda _: threading.Thread(target=self._run_fetch, args=("github",), daemon=True).start()),
                ft.ElevatedButton("📢 仅公众号", on_click=lambda _: threading.Thread(target=self._run_fetch, args=("wechat_mp",), daemon=True).start()),
            ], spacing=8, wrap=True),
            ft.Container(height=8),
            ft.Row([
                ft.ElevatedButton("📤 推送飞书", icon=ft.Icons.SEND,
                                  on_click=lambda _: threading.Thread(target=self._run_push, daemon=True).start()),
                ft.ElevatedButton("📤 推送公众号链接", icon=ft.Icons.ARTICLE,
                                  on_click=lambda _: threading.Thread(target=self._push_mp_only_inline, daemon=True).start()),
                ft.ElevatedButton("🧹 清空日志", icon=ft.Icons.CLEAR_ALL,
                                  on_click=lambda _: self._clear_log()),
            ], spacing=8, wrap=True),
            ft.Container(height=15),
            ft.Container(
                content=self.log_output,
                border=ft.border.all(1, ft.Colors.GREY_700),
                border_radius=8,
                padding=15,
                bgcolor=ft.Colors.BLACK38,
                expand=True,
            ),
        ], expand=True)

    def _clear_log(self):
        self.log_output.controls.clear()
        self.log_output.controls.append(
            ft.Text("📋 操作日志", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_300)
        )
        self.page.update()

    def _run_fetch_all(self):
        if self.running:
            return
        self._set_busy(True)
        self._log("开始抓取全部数据源...", "info")
        for src in ["aihot", "wechat_mp"]:
            self._run_fetch(src, threaded=False)
        self._log("全部数据源抓取完成", "ok")
        self._set_busy(False)

    def _run_fetch(self, source: str = "all", threaded: bool = True):
        if threaded and self.running:
            return
        if threaded:
            self._set_busy(True)
        try:
            src_map = {"aihot": ["aihot"], "github": ["github"], "wechat_mp": ["wechat_mp"], "all": None}
            items = fetch_sources(sources=src_map.get(source), log_func=self._log)
            if items:
                self.items = items
            self._log(f"共 {len(items)} 条", "ok" if items else "warn")
        except Exception as e:
            self._log(f"抓取异常: {e}", "err")
        if threaded:
            self._set_busy(False)

    def _run_fetch_and_push(self):
        if self.running:
            return
        self._set_busy(True)
        try:
            ok = fetch_and_push(log_func=self._log)
            if ok:
                self._log("流程完成 ✅", "ok")
        except Exception as e:
            self._log(f"流程异常: {e}", "err")
        self._set_busy(False)

    def _push_mp_only(self):
        threading.Thread(target=self._push_mp_only_inline, daemon=True).start()

    def _push_mp_only_inline(self):
        if self.running:
            return
        self._set_busy(True)
        try:
            self._log("获取公众号文章...", "info")
            fetch_and_push(sources=["wechat_mp"], log_func=self._log)
        except Exception as e:
            self._log(f"异常: {e}", "err")
        self._set_busy(False)

    def _run_push(self):
        if self.running or not self.items:
            if not self.items:
                self._log("没有数据可推送，请先抓取", "warn")
            return
        self._set_busy(True)
        try:
            if self.lark_chat_id:
                ok = push_ai_daily(self.items, chat_id=self.lark_chat_id, chat_name=None)
                self._log(f"飞书推送 {'成功 ✅' if ok else '失败 ❌'}", "ok" if ok else "err")
            else:
                self._log("未配置飞书群 ID", "warn")
        except Exception as e:
            self._log(f"推送异常: {e}", "err")
        self._set_busy(False)

    # ========== 设置页 ==========

    def _build_settings_page(self):
        """设置页面。"""
        chat_id_input = ft.TextField(
            label="飞书群 ID (oc_xxx)",
            value=self.lark_chat_id,
            width=400,
            hint_text="oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        )

        def save_lark_config(e):
            cid = chat_id_input.value.strip()
            if cid:
                config_dir = os.path.join(os.path.expanduser("~"), ".ainews")
                os.makedirs(config_dir, exist_ok=True)
                with open(os.path.join(config_dir, ".env.lark"), "w") as f:
                    f.write(f"LARK_CHAT_ID={cid}\n")
                self.lark_chat_id = cid
                self._log(f"飞书配置已保存: {cid[:20]}...", "ok")

        def open_lark_setup(e):
            script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts", "setup_lark_push.bat")
            if os.path.exists(script):
                os.startfile(script)
            else:
                self._log("初始化脚本未找到，请手动运行 scripts/setup_lark_push.bat", "warn")

        return ft.Column([
            ft.Text("⚙️ 设置", size=20, weight=ft.FontWeight.BOLD),
            ft.Container(height=5),
            ft.Text("飞书推送配置", size=15, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            chat_id_input,
            ft.Container(height=10),
            ft.Row([
                ft.ElevatedButton("💾 保存配置", on_click=save_lark_config),
                ft.OutlinedButton("🔄 运行初始化向导", on_click=open_lark_setup),
            ], spacing=10),
            ft.Container(height=25),
            ft.Text("数据源配置", size=15, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            ft.Text("编辑 config/sources.yaml 文件配置数据源参数", size=12, color=ft.Colors.GREY_400),
            ft.Container(height=20),
            ft.Text("环境变量", size=15, weight=ft.FontWeight.BOLD),
            ft.Container(height=10),
            ft.Text("GITHUB_TOKEN — GitHub API 令牌（提升速率限制至 5000 req/h）", size=12, color=ft.Colors.GREY_400),
            ft.Text("AIHOT_USER_AGENT — AIHOT API 请求 User-Agent", size=12, color=ft.Colors.GREY_400),
        ], expand=True, scroll=ft.ScrollMode.AUTO)


def main():
    """启动桌面控制台。"""
    ft.app(target=AIAggregatorApp)


if __name__ == "__main__":
    main()
