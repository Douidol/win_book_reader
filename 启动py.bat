@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
title 极简阅读器
echo 正在启动极简阅读器...
echo.
echo   Ctrl+`         唤出/隐藏
echo   Ctrl+Shift+H   老板键
echo   Ctrl+Shift+Q   退出
echo.
python main.py
