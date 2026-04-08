@echo off
REM ═══════════════════════════════════════════════════════════
REM HEKTO — Установка одной командой (Windows)
REM
REM Двойной клик или:  setup_hekto.bat
REM ═══════════════════════════════════════════════════════════

cd /d "%~dp0"

echo.
echo ╔═══════════════════════════════════════════════╗
echo ║          HEKTO — УСТАНОВКА                   ║
echo ║   Система поведенческого анализа трейдера    ║
echo ╚═══════════════════════════════════════════════╝
echo.

REM ── Check Python ─────────────────────────────────────────
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo   ✘ Python не найден!
    echo.
    echo   Установи Python 3.10+:
    echo     1. Скачай с https://www.python.org/downloads/
    echo     2. При установке ОБЯЗАТЕЛЬНО поставь галочку "Add Python to PATH"
    echo     3. Перезапусти этот скрипт
    echo.
    pause
    exit /b 1
)

REM ── Check Python version ─────────────────────────────────
python -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>nul
if %errorlevel% neq 0 (
    echo   ✘ Python слишком старый! Нужен Python 3.10+
    echo     Скачай: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo   ✔ Python найден
echo.

REM ── Run main setup ───────────────────────────────────────
python setup_hekto.py

echo.
pause
