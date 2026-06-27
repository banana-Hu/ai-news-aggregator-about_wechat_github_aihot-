@echo off
chcp 65001 >nul
title AI 情报聚合 — 开机自启安装

echo ============================================
echo   AI 情报聚合 · 开机自启
echo ============================================
echo.
echo 将创建一个启动脚本，每次开机自动执行一次日报抓取+推送。

for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON=%%i

echo @echo off > "%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ai_news_daily.bat"
echo %PYTHON% -m ainews daily >> "%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ai_news_daily.bat"

echo ✅ 已安装到启动文件夹
echo    路径: %USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\ai_news_daily.bat
echo.
echo 每次开机后约 30 秒会自动抓取 AI 资讯并推送飞书。
echo.
echo 移除方式：删除以上文件即可
echo ============================================
pause
