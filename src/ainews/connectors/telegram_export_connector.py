"""
Telegram 导出数据读取器。

读取 Telegram Desktop / iMe 导出的 JSON 格式聊天记录。
导出方式：设置 → 高级 → 导出数据 → JSON 格式
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ainews.connectors.base import BaseConnector
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# AI 关键词过滤
AI_KEYWORDS = [
    "AI", "Agent", "LLM", "GPT", "Claude", "OpenAI", "大模型",
    "prompt", "RAG", "MCP", "coding", "automation",
    "deepseek", "qwen", "多模态", "开源",
]

# 忽略的系统消息
IGNORE_PREFIXES = [
    "You created the group", "You joined", "joined the group",
    "left the group", "removed", "pinned", "changed the group",
]


class TelegramExportConnector(BaseConnector):
    """Telegram 导出数据连接器。"""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.export_path = self._resolve_export_path(config)
        self.max_per_chat = config.get("max_per_chat", 30)
        self.keywords = config.get("keywords", AI_KEYWORDS)

    def _resolve_export_path(self, config: dict | None = None) -> Path:
        """确定导出目录路径。"""
        cfg = config or {}
        if cfg.get("export_path"):
            return Path(cfg["export_path"])
        candidates = [
            Path.home() / "Desktop" / "Telegram Export",
            Path.home() / "Desktop" / "TelegramExport",
            Path.home() / "Downloads" / "Telegram Export",
            Path.home() / "Downloads" / "TelegramExport",
            Path("D:") / "hu" / "Telegram Desktop" / "tdata" / "export",
        ]
        for p in candidates:
            if p.exists():
                return p
        return candidates[0]

    def _load_result_file(self) -> dict | None:
        """加载 result.json（导出主文件）。"""
        files = [
            self.export_path / "result.json",
            self.export_path / "export.json",
        ]
        for f in files:
            if f.exists():
                logger.info(f"加载导出文件: {f}")
                return json.loads(f.read_text(encoding="utf-8"))
        return None

    def _get_chat_files(self) -> list[Path]:
        """获取每个聊天对应的 JSON 文件。"""
        # Telegram 导出每个聊天一个 JSON 文件
        pattern = self.export_path / "chats" / "*.json"
        chat_files = sorted(self.export_path.glob("chats/*.json"))
        if not chat_files:
            # 也可能是扁平结构
            chat_files = sorted(self.export_path.glob("*_messages.json"))
        return chat_files

    def fetch(self, **kwargs) -> list[NormalizedItem]:
        """读取导出数据，返回 AI 相关的消息条目。"""
        result = self._load_result_file()
        if not result:
            logger.warning(f"未找到导出文件: {self.export_path}")
            logger.info("请在 Telegram Desktop 设置 → 高级 → 导出数据，选择 JSON 格式导出")
            return []

        logger.info(f"读取导出数据: {self.export_path}")

        items = []

        # 方式 1: 读取 result.json 中的个人对话
        chats = result.get("chats", result.get("dialogs", []))
        if chats:
            items.extend(self._process_chats(chats))

        # 方式 2: 读取每个聊天的独立 JSON 文件
        chat_files = self._get_chat_files()
        for cf in chat_files:
            try:
                chat_data = json.loads(cf.read_text(encoding="utf-8"))
                items.extend(self._process_single_chat(chat_data))
            except Exception as e:
                logger.debug(f"跳过 {cf.name}: {e}")

        logger.info(f"找到 {len(items)} 条 AI 相关消息")
        return items

    def _process_chats(self, chats: list[dict]) -> list[NormalizedItem]:
        items = []
        for chat in chats:
            name = chat.get("name", "")
            if not self._is_ai_related(name):
                continue
            messages = chat.get("messages", [])
            for msg in messages[-self.max_per_chat:]:
                text = msg.get("text", "")
                if not text or len(text) < 20:
                    continue
                if not self._match_keywords(text):
                    continue
                if any(text.startswith(p) for p in IGNORE_PREFIXES):
                    continue

                items.append(self._msg_to_item(msg, name))
        return items

    def _process_single_chat(self, chat_data: dict) -> list[NormalizedItem]:
        name = chat_data.get("name", "")
        if not self._is_ai_related(name):
            return []

        messages = chat_data.get("messages", [])
        items = []
        for msg in messages[-self.max_per_chat:]:
            text = msg.get("text", "")
            if isinstance(text, list):
                text = "".join(
                    t.get("text", str(t)) if isinstance(t, dict) else str(t)
                    for t in text
                )
            if not text or len(text) < 20:
                continue
            if not self._match_keywords(text):
                continue
            if any(text.startswith(p) for p in IGNORE_PREFIXES):
                continue

            items.append(self._msg_to_item(msg, name))

        return items

    def _msg_to_item(self, msg: dict, group_name: str) -> NormalizedItem:
        text = msg.get("text", "")
        if isinstance(text, list):
            text = "".join(
                t.get("text", str(t)) if isinstance(t, dict) else str(t)
                for t in text
            )
        date = msg.get("date", "")
        msg_id = msg.get("id", 0)

        title = text.split("\n")[0][:80]
        if len(title) >= 80:
            title += "…"

        tags = self._tag(text)

        return NormalizedItem(
            source="telegram",
            source_type="telegram_message",
            title=title,
            url=f"https://t.me/{group_name}/{msg_id}",
            author=msg.get("from", group_name),
            published_at=date if date else None,
            summary=text[:200],
            content=text,
            tags=tags,
            raw={
                "group": group_name,
                "message_id": msg_id,
                "export": True,
            },
        )

    def _is_ai_related(self, name: str) -> bool:
        name_lower = name.lower()
        return any(kw.lower() in name_lower for kw in ["AI", "llm", "gpt", "大模型", "agent", "prompt", "ai", "tech"])

    def _match_keywords(self, text: str) -> bool:
        return any(kw.lower() in text.lower() for kw in self.keywords)

    def _tag(self, text: str) -> list[str]:
        tags = ["telegram"]
        t = text.lower()
        for kw in ["agent", "llm", "gpt", "claude", "rag", "mcp", "openai", "deepseek", "qwen"]:
            if kw in t:
                tags.append(kw.upper())
        return tags
