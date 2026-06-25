# AI News Aggregator 🤖

AI 情报聚合日报桌面控制台。自动抓取 **AIHOT（卡兹克）**、**GitHub**、**微信公众号** 的 AI 相关内容，去重评分后以富文本推送到飞书群。

## 快速开始

```bash
# 安装
pip install -r requirements.txt

# 启动桌面控制台
python -m ainews

# 或安装到系统后直接运行
pip install -e .
ainews
```

## 功能

### 桌面控制台（Flet UI）
- 左侧导航：概览 / 数据抓取 / 设置
- 一键抓取全部数据源
- 实时日志输出
- 一键推送飞书

### 命令行

```bash
# 抓取数据
python -m ainews fetch --source aihot --print

# 抓取并推送飞书
python -m ainews push
```

### 数据源

| 数据源 | 方式 | 内容 |
|--------|------|------|
| AIHOT | 公开 REST API | AI 资讯精选 + 日报 |
| GitHub | Search API v3 | AI 相关开源项目 |
| 微信公众号 | AIHOT 发现 + 直连抓取 | 公众号文章链接 |

### 推送
- 飞书 `post` 富文本格式
- 链接可点击
- 支持配置多个群

## 配置

### 飞书推送
```bash
# 运行初始化向导（Windows）
scripts\setup_lark_push.bat

# 或手动配置 .env.lark
echo LARK_CHAT_ID=oc_xxxxxxxxxxxx > .env.lark
```

### GitHub Token（推荐）
```bash
set GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

### 数据源配置
编辑 `config/sources.yaml` 可调整搜索关键词、抓取数量等。

## 项目结构

```
src/ainews/
├── connectors/       # 数据源连接器
│   ├── aihot_connector.py
│   ├── github_connector.py
│   ├── wechat_mp_connector.py
│   └── mp_extractor.py
├── services/         # 聚合服务
│   ├── dedup_service.py
│   ├── scoring_service.py
│   ├── source_fetch_service.py
│   └── push_service.py
├── schemas/          # 数据结构
│   └── normalized_item.py
└── ui/               # 桌面 UI
    └── app.py
```

## 测试

```bash
python -m pytest tests/ -v
```

## License

MIT
