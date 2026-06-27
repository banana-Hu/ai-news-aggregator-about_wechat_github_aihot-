@echo off
chcp 65001 >nul
title AI 情报聚合 — 定时任务安装

echo ============================================
echo   AI 情报聚合 · 定时任务安装工具
echo ============================================
echo.

echo [1/2] 查找 Python 路径...
for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON=%%i
echo Python: %PYTHON%

echo.
echo [2/2] 创建 Windows 定时任务（每天 08:30）...

set SCRIPT=%PYTHON% -m ainews.scheduler
set TASK_NAME=AI_News_Daily_Report

schtasks /Create /TN %TASK_NAME% /TR "%SCRIPT%" /SC DAILY /ST 08:30 /F

if %errorlevel% equ 0 (
    echo ✅ 定时任务创建成功
    echo.
    echo 任务名: %TASK_NAME%
    echo 执行时间: 每天 08:30
    echo 命令: python -m ainews.scheduler
    echo.
    echo 管理方式：
    echo   - 查看任务: taskschd.msc
    echo   - 删除任务: schtasks /Delete /TN %TASK_NAME% /F
    echo   - 手动运行: python -m ainews.scheduler
) else (
    echo ❌ 创建失败，请以管理员权限运行
)

echo.
echo ============================================
echo   也可以在 启动 文件夹里放快捷方式实现开机自启
echo ============================================
echo.
echo 1. Win+R 输入 shell:startup 回车
echo 2. 将本项目的 scheduler 快捷方式放入该文件夹
echo 3. 每次开机自动在后台运行 python -m ainews.scheduler --loop
echo.
pause
