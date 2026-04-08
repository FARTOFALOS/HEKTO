#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
# HEKTO — Установка одной командой (macOS / Linux)
#
# Этот скрипт:
#   1. Проверяет/устанавливает Python 3.10+
#   2. Проверяет/устанавливает FFmpeg
#   3. Запускает setup_hekto.py для остального
#
# Использование:
#   bash setup_hekto.sh
# ═══════════════════════════════════════════════════════════
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "╔═══════════════════════════════════════════════╗"
echo "║          HEKTO — УСТАНОВКА                   ║"
echo "║   Система поведенческого анализа трейдера     ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

# ── Detect OS ─────────────────────────────────────────────
OS="$(uname -s)"
echo "  ОС: $OS"

# ── Check / Install Python ────────────────────────────────
check_python() {
    local py=""
    # Try python3 first, then python
    for candidate in python3 python; do
        if command -v "$candidate" &>/dev/null; then
            local version
            version=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            local major minor
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                py="$candidate"
                echo "  ✔ Python $version найден: $(command -v "$candidate")"
                break
            fi
        fi
    done

    if [ -z "$py" ]; then
        echo "  ⚠ Python 3.10+ не найден — устанавливаю…"
        install_python
        py="python3"
    fi

    PYTHON="$py"
}

install_python() {
    if [ "$OS" = "Darwin" ]; then
        if command -v brew &>/dev/null; then
            echo "  → brew install python@3.12 …"
            brew install python@3.12
        else
            echo "  ✘ Homebrew не найден."
            echo "    Установи Homebrew:"
            echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
            echo "    Потом запусти этот скрипт снова."
            exit 1
        fi
    elif [ "$OS" = "Linux" ]; then
        if command -v apt-get &>/dev/null; then
            echo "  → sudo apt-get install -y python3 python3-venv python3-pip …"
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-venv python3-pip
        elif command -v dnf &>/dev/null; then
            echo "  → sudo dnf install -y python3 python3-pip …"
            sudo dnf install -y python3 python3-pip
        elif command -v pacman &>/dev/null; then
            echo "  → sudo pacman -S --noconfirm python python-pip …"
            sudo pacman -S --noconfirm python python-pip
        else
            echo "  ✘ Не найден пакетный менеджер. Установи Python 3.10+ вручную:"
            echo "    https://www.python.org/downloads/"
            exit 1
        fi
    fi
}

# ── Check / Install FFmpeg ────────────────────────────────
check_ffmpeg() {
    if command -v ffmpeg &>/dev/null; then
        echo "  ✔ FFmpeg найден"
        return
    fi

    echo "  ⚠ FFmpeg не найден — устанавливаю…"
    if [ "$OS" = "Darwin" ]; then
        if command -v brew &>/dev/null; then
            brew install ffmpeg
        else
            echo "  ✘ Установи Homebrew, затем: brew install ffmpeg"
            exit 1
        fi
    elif [ "$OS" = "Linux" ]; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y ffmpeg
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y ffmpeg
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm ffmpeg
        fi
    fi

    if command -v ffmpeg &>/dev/null; then
        echo "  ✔ FFmpeg установлен"
    else
        echo "  ✘ Не удалось установить FFmpeg. Установи вручную: https://ffmpeg.org"
        exit 1
    fi
}

# ── Install PortAudio (needed for sounddevice on Linux) ───
check_portaudio() {
    if [ "$OS" = "Linux" ]; then
        if command -v apt-get &>/dev/null; then
            if ! dpkg -s libportaudio2 &>/dev/null 2>&1; then
                echo "  → Устанавливаю PortAudio (нужен для записи)…"
                sudo apt-get install -y libportaudio2 portaudio19-dev
                echo "  ✔ PortAudio установлен"
            fi
        elif command -v dnf &>/dev/null; then
            if ! rpm -q portaudio &>/dev/null 2>&1; then
                echo "  → Устанавливаю PortAudio…"
                sudo dnf install -y portaudio portaudio-devel
            fi
        fi
    fi
}

# ── Run main setup ────────────────────────────────────────
check_python
check_ffmpeg
check_portaudio

echo ""
echo "  → Запускаю основную установку…"
echo ""

"$PYTHON" setup_hekto.py
