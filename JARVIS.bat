@echo off
title J.A.R.V.I.S.
cd /d "%~dp0"
.venv\Scripts\python.exe jarvis_main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERRO] JARVIS encerrou com codigo %errorlevel%
    pause
)
