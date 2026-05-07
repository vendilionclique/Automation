@echo off
chcp 65001 >nul
title 淘宝店透视插件自动化工具

echo ========================================
echo 淘宝店透视插件自动化工具
echo ========================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python环境，请先安装Python 3.10+
    pause
    exit /b 1
)

REM 检查依赖
pip show DrissionPage >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 检测到缺少依赖，正在安装...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    echo [成功] 依赖安装完成
    echo.
)

REM 运行主程序
python main.py %*

REM 如果程序异常退出，暂停以便查看错误信息
if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序运行失败，请查看上方错误信息
    pause
)
