"""
统一项目路径与资源配置。
所有模块通过此模块定位文件，不自行推导路径。
"""

import os
from pathlib import Path

# 包根目录: src/ainews/（core/ 的父目录）
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

# 项目根目录: ai-news-aggregator/
PROJECT_ROOT = PACKAGE_ROOT.parents[1]

# 配置文件
CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"

# 飞书推送配置
LARK_ENV_PATH = PROJECT_ROOT / ".env.lark"
USER_LARK_ENV_PATH = Path.home() / ".ainews" / ".env.lark"

# 脚本目录
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# Web 模板目录
TEMPLATES_DIR = PACKAGE_ROOT / "web" / "templates"


def read_lark_chat_id() -> str:
    """从 .env.lark 读取飞书群 ID。"""
    for p in [LARK_ENV_PATH, USER_LARK_ENV_PATH]:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line.startswith("LARK_CHAT_ID="):
                        return line.split("=", 1)[1].strip()
            except Exception:
                continue
    return ""


def ensure_user_config_dir():
    """确保 ~/.ainews/ 目录存在。"""
    path = Path.home() / ".ainews"
    path.mkdir(parents=True, exist_ok=True)
    return path
