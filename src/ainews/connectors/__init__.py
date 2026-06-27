"""连接器注册与工厂。"""

from .github_connector import GitHubConnector
from .aihot_connector import AIHOTConnector
from .wechat_mp_connector import WeChatMpConnector
from .telegram_export_connector import TelegramExportConnector

__all__ = ["GitHubConnector", "AIHOTConnector", "WeChatMpConnector",
           "TelegramExportConnector", "CONNECTORS", "get_connector"]

# 数据源注册表：新增数据源只需在此注册
CONNECTORS = {
    "aihot": (AIHOTConnector, {"max_items": 50}),
    "github": (GitHubConnector, {}),
    "wechat_mp": (WeChatMpConnector, {"extract_content": False, "max_articles": 20}),
    "telegram": (TelegramExportConnector, {"max_per_chat": 30}),
}

# "all" 包含的数据源（不含 GitHub，因无 Token 时速率过低）
ALL_SOURCES = ["aihot", "wechat_mp", "telegram"]


def get_connector(name: str, config: dict | None = None):
    """获取连接器实例。"""
    if name not in CONNECTORS:
        raise KeyError(f"未知数据源: {name}，可用: {list(CONNECTORS.keys())}")
    cls, defaults = CONNECTORS[name]
    cfg = dict(defaults)
    if config:
        cfg.update(config.get(name, {}))
    return cls(cfg)


def get_all_connectors(config: dict | None = None, sources: list[str] | None = None) -> list[tuple[str, object]]:
    """获取所有要抓取的连接器列表。"""
    names = sources or ALL_SOURCES
    result = []
    for name in names:
        if name in CONNECTORS:
            result.append((name, get_connector(name, config)))
    return result
