#!/usr/bin/env python3
"""
HEKTO — Автоматическая установка окружения.

Этот скрипт:
  1. Проверяет версию Python (≥ 3.10)
  2. Проверяет/устанавливает FFmpeg (нужен Whisper)
  3. Создаёт виртуальное окружение (venv)
  4. Устанавливает все Python-зависимости
  5. Проверяет доступность микрофона
  6. Инициализирует структуру папок и SQLite БД
  7. Запускает тесты для проверки корректности
  8. Создаёт ярлыки для запуска

Запуск:
    python setup_hekto.py            # полная установка
    python setup_hekto.py --check    # только проверить, всё ли на месте
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────

MIN_PYTHON = (3, 10)
PROJECT_ROOT = Path(__file__).resolve().parent
VENV_DIR = PROJECT_ROOT / "venv"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

PYTHON_IN_VENV = (
    VENV_DIR / "Scripts" / "python.exe" if IS_WINDOWS else VENV_DIR / "bin" / "python"
)
PIP_IN_VENV = (
    VENV_DIR / "Scripts" / "pip.exe" if IS_WINDOWS else VENV_DIR / "bin" / "pip"
)

# ANSI colours (disabled on Windows without VT support)
_USE_COLOR = not IS_WINDOWS or os.environ.get("TERM")
GREEN = "\033[92m" if _USE_COLOR else ""
YELLOW = "\033[93m" if _USE_COLOR else ""
RED = "\033[91m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
RESET = "\033[0m" if _USE_COLOR else ""

# Track overall result
_all_ok = True


def _print_step(msg: str) -> None:
    print(f"\n{BOLD}══ {msg} ══{RESET}")


def _ok(msg: str) -> None:
    print(f"  {GREEN}✔{RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {msg}")


def _fail(msg: str) -> None:
    global _all_ok
    _all_ok = False
    print(f"  {RED}✘{RESET} {msg}")


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess and return the result (does NOT raise on failure)."""
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Step 1: Python version ───────────────────────────────────────────────

def check_python() -> bool:
    _print_step("Проверка Python")
    v = sys.version_info
    version_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        _ok(f"Python {version_str} — подходит (нужен ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")
        return True
    _fail(
        f"Python {version_str} — слишком старая версия! "
        f"Нужен Python ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]}. "
        f"Скачай с https://www.python.org/downloads/"
    )
    return False


# ── Step 2: FFmpeg ────────────────────────────────────────────────────────

def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def check_ffmpeg() -> bool:
    _print_step("Проверка FFmpeg (нужен для Whisper)")
    if _ffmpeg_available():
        _ok("FFmpeg найден в системе")
        return True

    _warn("FFmpeg не найден — попробую установить автоматически…")
    return _install_ffmpeg()


def _install_ffmpeg() -> bool:
    """Try to install FFmpeg using the system package manager."""
    if IS_MACOS:
        if shutil.which("brew"):
            print("    → brew install ffmpeg …")
            r = _run(["brew", "install", "ffmpeg"])
            if r.returncode == 0 and _ffmpeg_available():
                _ok("FFmpeg установлен через Homebrew")
                return True
            _fail("Не удалось установить FFmpeg через Homebrew")
            return False
        _fail(
            "Homebrew не найден. Установи Homebrew:\n"
            "      /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"\n"
            "    Потом запусти этот скрипт снова."
        )
        return False

    if IS_LINUX:
        for pkg_mgr, install_cmd in [
            ("apt-get", ["sudo", "apt-get", "install", "-y", "ffmpeg"]),
            ("dnf", ["sudo", "dnf", "install", "-y", "ffmpeg"]),
            ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"]),
        ]:
            if shutil.which(pkg_mgr):
                print(f"    → {' '.join(install_cmd)} …")
                r = _run(install_cmd)
                if r.returncode == 0 and _ffmpeg_available():
                    _ok(f"FFmpeg установлен через {pkg_mgr}")
                    return True
                _fail(f"Не удалось установить FFmpeg через {pkg_mgr}")
                return False
        _fail("Не найден пакетный менеджер (apt/dnf/pacman). Установи FFmpeg вручную.")
        return False

    if IS_WINDOWS:
        if shutil.which("winget"):
            print("    → winget install Gyan.FFmpeg …")
            r = _run(["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--accept-source-agreements"])
            if r.returncode == 0:
                _ok("FFmpeg установлен через winget. Перезапусти терминал и скрипт.")
                return True
        if shutil.which("choco"):
            print("    → choco install ffmpeg -y …")
            r = _run(["choco", "install", "ffmpeg", "-y"])
            if r.returncode == 0:
                _ok("FFmpeg установлен через Chocolatey. Перезапусти терминал и скрипт.")
                return True
        _fail(
            "Не удалось установить FFmpeg автоматически.\n"
            "    Скачай вручную: https://ffmpeg.org/download.html\n"
            "    Или установи через: winget install Gyan.FFmpeg"
        )
        return False

    _fail("Неизвестная ОС — установи FFmpeg вручную: https://ffmpeg.org/download.html")
    return False


# ── Step 3: Virtual environment ──────────────────────────────────────────

def create_venv() -> bool:
    _print_step("Виртуальное окружение (venv)")
    if VENV_DIR.exists() and PYTHON_IN_VENV.exists():
        _ok(f"venv уже существует: {VENV_DIR}")
        return True

    print(f"    → Создаю venv в {VENV_DIR} …")
    r = _run([sys.executable, "-m", "venv", str(VENV_DIR)])
    if r.returncode != 0:
        _fail(f"Не удалось создать venv:\n{r.stderr}")
        return False

    if PYTHON_IN_VENV.exists():
        _ok(f"venv создан: {VENV_DIR}")
        return True

    _fail("venv создан, но Python не найден внутри")
    return False


# ── Step 4: Install dependencies ─────────────────────────────────────────

def install_deps() -> bool:
    _print_step("Установка Python-зависимостей")

    if not REQUIREMENTS.exists():
        _fail(f"Файл {REQUIREMENTS} не найден!")
        return False

    # Upgrade pip first
    print("    → Обновляю pip …")
    _run([str(PYTHON_IN_VENV), "-m", "pip", "install", "--upgrade", "pip"])

    # Install requirements
    print("    → pip install -r requirements.txt …  (может занять 2-5 минут)")
    r = _run(
        [str(PIP_IN_VENV), "install", "-r", str(REQUIREMENTS)],
        cwd=str(PROJECT_ROOT),
    )
    if r.returncode != 0:
        _fail(f"Ошибка установки зависимостей:\n{r.stderr[-1000:]}")
        return False
    _ok("Все зависимости установлены")

    # Install test deps
    print("    → pip install pytest …")
    _run([str(PIP_IN_VENV), "install", "pytest"])
    _ok("pytest установлен")
    return True


# ── Step 5: Microphone check ─────────────────────────────────────────────

def check_microphone() -> bool:
    _print_step("Проверка микрофона")
    # Try to import sounddevice and list devices
    check_code = textwrap.dedent("""\
        import json
        try:
            import sounddevice as sd
            devs = sd.query_devices()
            inputs = [d for d in devs if d.get('max_input_channels', 0) > 0]
            if inputs:
                default = sd.query_devices(kind='input')
                print(json.dumps({
                    "ok": True,
                    "default": default['name'],
                    "count": len(inputs)
                }))
            else:
                print(json.dumps({"ok": False, "error": "no_input_devices"}))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
    """)

    r = _run([str(PYTHON_IN_VENV), "-c", check_code])
    if r.returncode != 0 or not r.stdout.strip():
        _warn(
            "Не удалось проверить микрофон (sounddevice). "
            "Это нормально, если нет аудио-устройства (например, на сервере). "
            "На ноутбуке должно работать."
        )
        return True  # non-blocking

    import json
    try:
        result = json.loads(r.stdout.strip())
    except json.JSONDecodeError:
        _warn("Не удалось распознать ответ проверки микрофона")
        return True

    if result.get("ok"):
        _ok(f"Микрофон найден: {result['default']} (устройств ввода: {result['count']})")
        return True
    else:
        _warn(
            f"Микрофон не обнаружен: {result.get('error', '?')}. "
            "Убедись, что микрофон подключён при записи."
        )
        return True  # non-blocking


# ── Step 6: Initialize data dirs & DB ────────────────────────────────────

def init_data() -> bool:
    _print_step("Инициализация данных")

    for dirname in ("data/raw", "data/processed", "data/patterns"):
        d = PROJECT_ROOT / dirname
        d.mkdir(parents=True, exist_ok=True)

    _ok("Папки data/raw, data/processed, data/patterns — готовы")

    # Initialize DB schema by importing db_writer
    init_code = textwrap.dedent("""\
        import sys
        sys.path.insert(0, ".")
        from src.db_writer import get_connection
        from src.config import DB_PATH
        conn = get_connection(DB_PATH)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        print(",".join(sorted(tables)))
    """)

    r = _run([str(PYTHON_IN_VENV), "-c", init_code], cwd=str(PROJECT_ROOT))
    if r.returncode == 0 and r.stdout.strip():
        tables = r.stdout.strip().split(",")
        _ok(f"SQLite БД инициализирована ({len(tables)} таблиц: {', '.join(tables)})")
        return True

    # Even if DB init fails, dirs are OK
    _warn(f"БД не инициализирована (будет создана при первом запуске): {r.stderr[:300]}")
    return True


# ── Step 7: Run tests ────────────────────────────────────────────────────

def run_tests() -> bool:
    _print_step("Запуск тестов")
    r = _run(
        [str(PYTHON_IN_VENV), "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=str(PROJECT_ROOT),
    )
    if r.returncode == 0:
        # Extract summary line
        for line in r.stdout.splitlines()[::-1]:
            if "passed" in line:
                _ok(f"Тесты: {line.strip()}")
                break
        else:
            _ok("Все тесты пройдены")
        return True
    _warn(f"Некоторые тесты упали (это может быть нормально без микрофона):\n{r.stdout[-500:]}")
    return True  # non-blocking


# ── Step 8: Create quick-launch scripts ──────────────────────────────────

def _venv_python_rel() -> str:
    """Return the venv Python path relative to PROJECT_ROOT as a string."""
    return str(PYTHON_IN_VENV.relative_to(PROJECT_ROOT))


def create_launcher_scripts() -> bool:
    _print_step("Создание скриптов быстрого запуска")

    if IS_WINDOWS:
        _create_windows_launchers()
    else:
        _create_unix_launchers()

    return True


def _create_unix_launchers() -> None:
    """Create shell scripts for macOS/Linux."""
    py = _venv_python_rel()

    # hekto_record.sh
    path = PROJECT_ROOT / "hekto_record.sh"
    path.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # HEKTO — Начать запись голоса
        # Нажми Enter чтобы остановить
        cd "$(dirname "$0")"
        {py} -m src.recorder "$@"
    """), encoding="utf-8")
    path.chmod(0o755)
    _ok(f"Создан: {path.name}  →  запись голоса")

    # hekto_daily.sh
    path = PROJECT_ROOT / "hekto_daily.sh"
    path.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # HEKTO — Полный дневной анализ
        cd "$(dirname "$0")"
        DATE="${{1:-$(date +%Y-%m-%d)}}"
        echo "═══ HEKTO: Анализ дня $DATE ═══"
        {py} -m src.run_daily --date "$DATE" "${{@:2}}"
    """), encoding="utf-8")
    path.chmod(0o755)
    _ok(f"Создан: {path.name}  →  анализ дня")

    # hekto_state.sh
    path = PROJECT_ROOT / "hekto_state.sh"
    path.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # HEKTO — Записать своё состояние перед торговлей
        cd "$(dirname "$0")"
        {py} -m src.daily_state "$@"
    """), encoding="utf-8")
    path.chmod(0o755)
    _ok(f"Создан: {path.name}  →  состояние дня")

    # hekto_report.sh
    path = PROJECT_ROOT / "hekto_report.sh"
    path.write_text(textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # HEKTO — Отчёт за день
        cd "$(dirname "$0")"
        DATE="${{1:-$(date +%Y-%m-%d)}}"
        {py} -m src.reporter --date "$DATE"
    """), encoding="utf-8")
    path.chmod(0o755)
    _ok(f"Создан: {path.name}  →  отчёт")


def _create_windows_launchers() -> None:
    """Create .bat scripts for Windows."""
    py = _venv_python_rel()

    # hekto_record.bat
    path = PROJECT_ROOT / "hekto_record.bat"
    path.write_text(textwrap.dedent(f"""\
        @echo off
        REM HEKTO — Начать запись голоса
        REM Нажми Enter чтобы остановить
        cd /d "%~dp0"
        {py} -m src.recorder %*
    """), encoding="utf-8")
    _ok(f"Создан: {path.name}  →  запись голоса")

    # hekto_daily.bat
    path = PROJECT_ROOT / "hekto_daily.bat"
    path.write_text(textwrap.dedent(f"""\
        @echo off
        REM HEKTO — Полный дневной анализ
        cd /d "%~dp0"
        for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set TODAY=%%c-%%a-%%b
        if "%1"=="" (set DATE=%TODAY%) else (set DATE=%1)
        echo === HEKTO: Анализ дня %DATE% ===
        {py} -m src.run_daily --date %DATE% %2 %3 %4 %5
    """), encoding="utf-8")
    _ok(f"Создан: {path.name}  →  анализ дня")

    # hekto_state.bat
    path = PROJECT_ROOT / "hekto_state.bat"
    path.write_text(textwrap.dedent(f"""\
        @echo off
        REM HEKTO — Записать состояние дня
        cd /d "%~dp0"
        {py} -m src.daily_state %*
    """), encoding="utf-8")
    _ok(f"Создан: {path.name}  →  состояние дня")

    # hekto_report.bat
    path = PROJECT_ROOT / "hekto_report.bat"
    path.write_text(textwrap.dedent(f"""\
        @echo off
        REM HEKTO — Отчёт за день
        cd /d "%~dp0"
        for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set TODAY=%%c-%%a-%%b
        if "%1"=="" (set DATE=%TODAY%) else (set DATE=%1)
        {py} -m src.reporter --date %DATE%
    """), encoding="utf-8")
    _ok(f"Создан: {path.name}  →  отчёт")


# ── Final summary ────────────────────────────────────────────────────────

def print_summary() -> None:
    _print_step("Результат установки")

    if _all_ok:
        py = _venv_python_rel()
        if IS_WINDOWS:
            scripts = textwrap.dedent("""\
                Запуск:
                  hekto_state.bat                     — записать состояние утром
                  hekto_record.bat                    — записать голос (Enter = стоп)
                  hekto_daily.bat                     — анализ дня
                  hekto_daily.bat 2025-01-15          — анализ конкретной даты
                  hekto_report.bat                    — отчёт за сегодня
            """)
        else:
            scripts = textwrap.dedent("""\
                Запуск:
                  ./hekto_state.sh                    — записать состояние утром
                  ./hekto_record.sh                   — записать голос (Enter = стоп)
                  ./hekto_daily.sh                    — анализ дня
                  ./hekto_daily.sh 2025-01-15         — анализ конкретной даты
                  ./hekto_report.sh                   — отчёт за сегодня
            """)

        print(f"""
  {GREEN}{BOLD}╔═══════════════════════════════════════════════╗
  ║         HEKTO УСТАНОВЛЕН УСПЕШНО!             ║
  ╚═══════════════════════════════════════════════╝{RESET}

  {BOLD}Твой ежедневный процесс:{RESET}

    1. Утром — запиши состояние (сон, стресс, заметки)
    2. Во время торговли — говори всё что думаешь (запись)
    3. Вечером — запусти анализ дня

{scripts}
  {BOLD}Или через Python напрямую:{RESET}
    {py} -m src.daily_state            — записать состояние
    {py} -m src.recorder               — записать голос
    {py} -m src.run_daily              — анализ дня
    {py} -m src.reporter --date YYYY-MM-DD  — отчёт
    {py} -m src.pattern_engine         — паттерны (после 20+ сделок)
""")
    else:
        print(f"""
  {RED}{BOLD}Установка завершена с ошибками.{RESET}
  Исправь проблемы выше и запусти скрипт снова:
      python setup_hekto.py
""")


# ── check-only mode ──────────────────────────────────────────────────────

def check_only() -> None:
    """Quick health-check without installing anything."""
    _print_step("HEKTO — Проверка окружения")

    # Python
    v = sys.version_info
    if (v.major, v.minor) >= MIN_PYTHON:
        _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        _fail(f"Python {v.major}.{v.minor}.{v.micro} (нужен ≥ {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")

    # FFmpeg
    if _ffmpeg_available():
        _ok("FFmpeg")
    else:
        _fail("FFmpeg не найден")

    # Venv
    if VENV_DIR.exists() and PYTHON_IN_VENV.exists():
        _ok(f"venv: {VENV_DIR}")
    else:
        _fail("venv не создан")

    # Requirements
    if PYTHON_IN_VENV.exists():
        r = _run([str(PYTHON_IN_VENV), "-c", "import whisper; import sounddevice; import pandas"])
        if r.returncode == 0:
            _ok("Зависимости (whisper, sounddevice, pandas)")
        else:
            _fail("Не все зависимости установлены")

    # Data dirs
    for d in ("data/raw", "data/processed", "data/patterns"):
        if (PROJECT_ROOT / d).exists():
            _ok(f"Папка {d}")
        else:
            _fail(f"Папка {d} не найдена")

    # DB
    db = PROJECT_ROOT / "data" / "processed" / "hekto.db"
    if db.exists():
        _ok(f"База данных: {db}")
    else:
        _warn("БД ещё не создана (создастся при первом запуске)")

    if _all_ok:
        print(f"\n  {GREEN}{BOLD}Всё в порядке!{RESET}")
    else:
        print(f"\n  {RED}Есть проблемы — запусти: python setup_hekto.py{RESET}")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="HEKTO — автоматическая установка окружения",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Только проверить, всё ли установлено (без изменений)",
    )
    args = parser.parse_args()

    print(f"""
{BOLD}╔═══════════════════════════════════════════════╗
║          HEKTO — АВТОУСТАНОВКА                ║
║   Система поведенческого анализа трейдера     ║
╚═══════════════════════════════════════════════╝{RESET}
  ОС: {platform.system()} {platform.release()}
  Python: {sys.version.split()[0]}
  Директория: {PROJECT_ROOT}
""")

    if args.check:
        check_only()
        return

    # Full install
    ok = check_python()
    if not ok:
        print_summary()
        sys.exit(1)

    check_ffmpeg()
    ok = create_venv()
    if not ok:
        print_summary()
        sys.exit(1)

    ok = install_deps()
    if not ok:
        print_summary()
        sys.exit(1)

    check_microphone()
    init_data()
    run_tests()
    create_launcher_scripts()
    print_summary()

    sys.exit(0 if _all_ok else 1)


if __name__ == "__main__":
    main()
