#!/usr/bin/env bash
# Lark AI 日报推送工具 - 初始化脚本 (macOS/Linux)
set -e

echo "============================================"
echo "  Lark AI 日报推送工具 - 初始化"
echo "============================================"
echo ""

# 1. 认证
echo "[1/3] 检查 Lark 认证状态..."
if lark-cli auth status &>/dev/null; then
    echo "✅ 已认证，跳过此步骤"
else
    echo "❌ 尚未认证"
    echo ""
    echo "正在启动 Lark 应用创建流程..."
    echo ""
    echo "⚠️  浏览器会打开飞书开放平台，请按指引完成配置"
    echo ""
    lark-cli config init --new --brand feishu
    echo "✅ 认证成功"
fi

# 2. 搜索群
echo ""
echo "[2/3] 搜索目标群..."
read -p "请输入群名称（默认: AI 日报）: " CHAT_NAME
CHAT_NAME=${CHAT_NAME:-"AI 日报"}

echo "正在搜索群: ${CHAT_NAME} ..."
lark-cli im +chat-search --query "${CHAT_NAME}" --format json > /tmp/lark_chat.json 2>&1 || {
    echo "❌ 搜索失败"
    cat /tmp/lark_chat.json
    exit 1
}

echo "✅ 搜索完成"
echo ""
echo "找到以下群："
python3 -c "
import sys, json
data = json.load(open('/tmp/lark_chat.json'))
items = data.get('items', data if isinstance(data, list) else [])
for i, c in enumerate(items[:5]):
    print(f'  {i+1}. {c.get(\"name\", \"?\")} (ID: {c.get(\"chat_id\", \"?\")})')
"

read -p "请选择群编号（直接回车选第1个）: " CHAT_SELECT
CHAT_SELECT=${CHAT_SELECT:-1}

CHAT_ID=$(python3 -c "
import json
data = json.load(open('/tmp/lark_chat.json'))
items = data.get('items', data if isinstance(data, list) else [])
idx = int('${CHAT_SELECT}') - 1
print(items[idx]['chat_id'])
" 2>/dev/null) || {
    echo "❌ 选择失败，使用第一个群"
    CHAT_ID=$(python3 -c "
import json
data = json.load(open('/tmp/lark_chat.json'))
items = data.get('items', data if isinstance(data, list) else [])
print(items[0]['chat_id'])
")
}

echo "✅ 选定群 ID: ${CHAT_ID}"

# 3. 保存配置
echo ""
echo "[3/3] 保存配置..."
cat > .env.lark << EOF
# Lark 推送配置
LARK_CHAT_ID=${CHAT_ID}
LARK_CHAT_NAME=${CHAT_NAME}
EOF

echo "✅ 配置已保存到 .env.lark"
echo ""
echo "============================================"
echo "  初始化完成！现在可以使用推送功能了"
echo "============================================"
echo ""
echo "使用方式："
echo "  python run_fetch_ai_sources.py --push"
echo ""
