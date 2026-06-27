"""
Telegram 连接器（MTProto 客户端模式）。

通过用户账号读取群组/频道的 AI 相关消息，
转换为 NormalizedItem 供日报系统消费。

首次运行：需要 api_id / api_hash / 手机号登录
后续运行：自动使用缓存的 session 文件
"""

import os
import re
import logging
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import Message
from ainews.connectors.base import BaseConnector
from ainews.schemas.normalized_item import NormalizedItem

logger = logging.getLogger(__name__)

# session 文件路径
SESSION_PATH = Path.home() / ".ainews" / "telegram.session"

# 默认 AI 相关关键词筛选
AI_KEYWORDS = [
    "AI", "Agent", "LLM", "GPT", "Claude", "OpenAI", "大模型",
    "prompt", "RAG", "MCP", "coding", "workflow", "自动化",
    "deepseek", "qwen", "多模态", "开源", "模型发布",
]

# 消息长度下限（太短的不收录）
MIN_MESSAGE_LENGTH = 20


class TelegramConnector(BaseConnector):
    """Telegram 群组/频道消息连接器。"""

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.api_id = int(config.get("api_id") or os.environ.get("TG_API_ID", "0"))
        self.api_hash = config.get("api_hash") or os.environ.get("TG_API_HASH", "")
        self.phone = config.get("phone") or os.environ.get("TG_PHONE", "")
        self.groups = config.get("groups", [])  # 群组/频道名称列表
        self.max_per_group = config.get("max_per_group", 20)
        self.keywords = config.get("keywords", AI_KEYWORDS)
        self.session_path = config.get("session_path", str(SESSION_PATH))

    def _get_client(self) -> TelegramClient | None:
        if not self.api_id or not self.api_hash:
            self.logger.error("未配置 TG_API_ID / TG_API_HASH")
            return None
        return TelegramClient(self.session_path, self.api_id, self.api_hash)

    def fetch(self, **kwargs) -> list[NormalizedItem]:
        client = self._get_client()
        if not client:
            return []

        items = []

        async def _fetch():
            await client.start(phone=self.phone)
            dialogs = await client.get_dialogs()

            for dialog in dialogs:
                name = dialog.name or ""
                # 筛选目标群
                if self.groups and name not in self.groups:
                    continue
                if not self.groups and not self._is_ai_group(name):
                    continue

                self.logger.info(f"读取群组: {name}")

                try:
                    messages = await client.get_messages(dialog, limit=self.max_per_group)
                    for msg in messages:
                        if not isinstance(msg, Message):
                            continue
                        text = msg.message
                        if not text or len(text) < MIN_MESSAGE_LENGTH:
                            continue
                        if not self._match_keywords(text):
                            continue

                        item = NormalizedItem(
                            source="telegram",
                            source_type="telegram_message",
                            title=self._extract_title(text, name),
                            url=f"https://t.me/{getattr(dialog.entity, 'username', '')}/{msg.id}" if hasattr(dialog.entity, 'username') else "",
                            author=name,
                            published_at=msg.date.isoformat() if msg.date else None,
                            summary=text[:200],
                            content=text,
                            tags=self._tag(text),
                            raw={
                                "group": name,
                                "message_id": msg.id,
                                "views": getattr(msg, "views", 0) or 0,
                                "forwards": getattr(msg, "forwards", 0) or 0,
                            },
                        )
                        items.append(item)
                except Exception as e:
                    self.logger.error(f"读取群组 {name} 失败: {e}")

            await client.disconnect()

        import asyncio
        asyncio.run(_fetch())

        self.logger.info(f"Telegram 抓取: {len(items)} 条")
        return items

    def _is_ai_group(self, name: str) -> bool:
        """判断群名是否 AI 相关。"""
        name_lower = name.lower()
        return any(kw.lower() in name_lower for kw in ["AI", "LLM", "GPT", "大模型", "Agent", "prompt", "AI"])

    def _match_keywords(self, text: str) -> bool:
        """消息是否包含 AI 关键词。"""
        return any(kw.lower() in text.lower() for kw in self.keywords)

    def _extract_title(self, text: str, group_name: str) -> str:
        """从消息文本提取标题。"""
        # 取第一行或前 60 字
        first_line = text.split("\n")[0].strip()
        if len(first_line) > 80:
            first_line = first_line[:80] + "…"
        return first_line or f"[{group_name} 消息]"

    def _tag(self, text: str) -> list[str]:
        """给消息打 AI 标签。"""
        tags = ["telegram"]
        text_lower = text.lower()
        for kw in ["agent", "llm", "gpt", "claude", "rag", "mcp", "openai", "deepseek", "qwen"]:
            if kw in text_lower:
                tags.append(kw.upper())
        return tags
