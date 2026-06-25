# AI News Aggregator 🤖

> AI 情报聚合日报系统 — 桌面控制台。自动抓取多源 AI 信息，去重评分后以富文本推送到飞书群。

---

## 数据源

| 数据源 | 接入方式 | 抓取内容 | 是否需要认证 |
|--------|----------|----------|-------------|
| **[AIHOT](https://aihot.virxact.com)** (卡兹克) | 公开 REST API | AI 资讯精选、AI 日报、模型发布、产品更新、行业动态、论文研究 | ❌ 无需 |
| **GitHub** | Search API v3 | 热门 AI 开源项目（按关键词搜索：Agent/LLM/RAG/MCP 等） | ⚠️ 推荐 Token |
| **微信公众号** | AIHOT 发现 + 直连 HTTPS 抓取 | 公众号 AI 文章（标题 + 链接），支持指定账号跟踪 | ❌ 无需 |

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 启动桌面控制台

```bash
python -m ainews
```

![控制台界面](https://via.placeholder.com/800x500/1a1a2e/ffffff?text=AI+News+Aggregator+Console)

### 命令行模式

```bash
# 抓取 AIHOT 最新资讯
python -m ainews fetch --source aihot --print

# 抓取并推送飞书
python -m ainews push

# 抓取全部数据源保存到文件
python -m ainews fetch --output news.json
```

---

## 桌面控制台功能

### 📊 概览页
- 各数据源状态卡片
- 快速操作按钮：一键抓取、抓取并推送、仅推公众号
- 飞书推送配置状态

### 📡 数据抓取页
- **数据源选择**：支持单独抓取 AIHOT / GitHub / 公众号
- **一键全量**：同时抓取所有数据源
- **推送飞书**：抓取结果可直接推送到已配置的飞书群
- **实时日志**：操作日志实时输出，支持清空

### ⚙️ 设置页
- 飞书群 ID 配置
- 飞书推送初始化向导
- 数据源配置指引
- 环境变量说明

---

## 配置

### 1. 飞书推送（首次使用必需）

```bash
# Windows — 运行初始化向导
scripts\setup_lark_push.bat

# macOS / Linux
chmod +x scripts/setup_lark_push.sh && ./scripts/setup_lark_push.sh

# 或手动创建 .env.lark
echo LARK_CHAT_ID=oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx > .env.lark
```

### 2. GitHub Token（强烈推荐）

未设置 Token 时速率限制为 **60 次/小时**，设置后提升至 **5000 次/小时**。

```bash
# Windows
set GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx

# macOS / Linux (推荐写入 shell 配置文件)
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

### 3. 数据源参数

编辑 `config/sources.yaml`：

```yaml
aihot:
  max_items: 50
  days_back: 3

github:
  queries:
    - "AI Agent"
    - "LLM"
    - "MCP"
    - "RAG"
  max_per_query: 10

wechat_mp:
  search_keywords:
    - "AI"
    - "Agent"
    - "大模型"
  accounts:
    - name: "数字生命卡兹克"
```

---

## 推送格式

采用 **飞书 post 富文本** 格式，每条消息包含：

```
🤖 AI 情报日报 · 2026-06-25
共 25 条内容

━━━━━━━━━━━━━━━━━━

🔥 AI 资讯精选（19 条）
──────────────────────────
1. 标题标题
   来源: xxx  |  评分: 55
   摘要内容摘要内容摘要内容
   查看原文 →                              ← 可点击链接

📢 公众号文章精选（6 条）
──────────────────────────
1. 文章标题
   来源: 公众号名称
   阅读全文 →                              ← 可点击链接
```

---

## 项目架构

```
ai-news-aggregator/
├── src/ainews/                    # 主包
│   ├── __init__.py
│   ├── __main__.py                # CLI + 桌面入口
│   ├── connectors/                # 数据源连接器
│   │   ├── base.py                # BaseConnector 抽象基类
│   │   ├── aihot_connector.py     # AIHOT 公开 API 接入
│   │   ├── github_connector.py    # GitHub Search API v3
│   │   ├── wechat_mp_connector.py # 公众号文章发现 + 抓取
│   │   └── mp_extractor.py        # 公众号正文提取 (trafilatura)
│   ├── services/                  # 聚合服务
│   │   ├── dedup_service.py       # URL/标题/内容 三层去重
│   │   ├── scoring_service.py     # 规则评分 (0-100)
│   │   ├── source_fetch_service.py# 统一调度入口
│   │   └── push_service.py        # 飞书 post 富文本推送
│   ├── schemas/
│   │   └── normalized_item.py     # 统一数据结构
│   └── ui/
│       └── app.py                 # Flet 桌面 UI
├── config/
│   └── sources.yaml               # 数据源配置
├── tests/                         # 55 个单元测试
├── scripts/                       # 初始化脚本
├── pyproject.toml                 # 构建配置
├── .env.lark.example              # 飞书配置模板
└── requirements.txt
```

## 处理流程

```
AIHOT API ──┐
GitHub API ─┼──→ NormalizedItem → 去重 (URL/标题/内容)
公众号 ────┘         │
                     ▼
              规则评分 (Star/关键词/时效)
                     │
                     ▼
        build_post_content() → post JSON
                     │
                     ▼
              lark-cli → 飞书群 ✅
```

## 测试

```bash
# 运行全部 55 个测试
python -m pytest tests/ -v

# 指定模块
python -m pytest tests/test_aihot_connector.py -v
python -m pytest tests/test_wechat_mp_connector.py -v
```

## 环境要求

- Python ≥ 3.10
- Windows / macOS / Linux
- lark-cli（飞书推送用，可选）

## Tech Stack

- **Python 3.11+** — 核心逻辑
- **Flet** — 桌面 UI（Flutter 渲染）
- **trafilatura** — 公众号文章正文提取
- **GitHub Search API v3** — 开源项目搜索
- **AIHOT REST API** — AI 资讯聚合
- **lark-cli** — 飞书消息推送

## License

MIT
