@echo off
chcp 65001 >nul
title Lark AI 日报推送工具 - 初始化
echo ============================================
echo   Lark AI 日报推送工具 - 初始化
echo ============================================
echo.

:check_auth
echo [1/3] 检查 Lark 认证状态...
lark-cli auth status >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ 已认证，跳过此步骤
    goto check_chat
)

echo ❌ 尚未认证
echo.
echo 正在启动 Lark 应用创建流程...
echo.
echo ⚠️  请按以下步骤操作：
echo  1. 浏览器会自动打开，登录飞书开放平台
echo  2. 创建企业自建应用（或选择已有应用）
echo  3. 获取 App ID 和 App Secret
echo  4. 返回终端粘贴
echo.
echo 🔗 浏览器打开后，如果未自动跳转，请手动复制 URL 打开
echo.
pause
echo.
lark-cli config init --new --brand feishu
if %errorlevel% neq 0 (
    echo ❌ 认证失败，请重试
    pause
    exit /b 1
)
echo ✅ 认证成功

:check_chat
echo.
echo [2/3] 搜索目标群...
set /p CHAT_NAME=请输入群名称（默认: AI 日报）: 
if "%CHAT_NAME%"=="" set CHAT_NAME=AI 日报

echo 正在搜索群: %CHAT_NAME% ...
lark-cli im +chat-search --query "%CHAT_NAME%" --format json > %temp%\lark_chat.json 2>&1
if %errorlevel% neq 0 (
    echo ❌ 搜索失败，请确认群名称
    type %temp%\lark_chat.json
    pause
    exit /b 1
)

echo ✅ 搜索完成
echo.
echo 找到以下群：
type %temp%\lark_chat.json | python -c "import sys,json; data=json.load(sys.stdin); items=data.get('items',data if isinstance(data,list) else []); [print(f'  {i+1}. {c.get(\"name\",\"?\")} (ID: {c.get(\"chat_id\",\"?\")})') for i,c in enumerate(items[:5])]"
echo.
set /p CHAT_SELECT=请选择群编号（直接回车选第1个）: 
if "%CHAT_SELECT%"=="" set CHAT_SELECT=1

for /f "tokens=*" %%a in ('python -c "import sys,json; data=json.load(open(r'%temp%\lark_chat.json')); items=data.get('items',data if isinstance(data,list) else []); idx=int('%CHAT_SELECT%')-1; print(items[idx].get('chat_id',''))" 2^>nul') do set CHAT_ID=%%a
if "%CHAT_ID%"=="" (
    echo ❌ 选择失败，将使用第一个群
    for /f "tokens=*" %%a in ('python -c "import sys,json; data=json.load(open(r'%temp%\lark_chat.json')); items=data.get('items',data if isinstance(data,list) else []); print(items[0].get('chat_id',''))"') do set CHAT_ID=%%a
)

echo ✅ 选定群 ID: %CHAT_ID%

:save_config
echo.
echo [3/3] 保存配置...
(
    echo # Lark 推送配置
    echo LARK_CHAT_ID=%CHAT_ID%
    echo LARK_CHAT_NAME=%CHAT_NAME%
) > .env.lark

echo ✅ 配置已保存到 .env.lark
echo.
echo ============================================
echo   初始化完成！现在可以使用推送功能了
echo ============================================
echo.
echo 使用方式：
echo   python run_fetch_ai_sources.py --push
echo.
pause
