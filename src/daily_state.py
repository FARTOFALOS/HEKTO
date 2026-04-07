"""
HEKTO daily state CLI.

Allows the trader to record their daily physical/mental state before
the trading session starts. This data is stored in the ``daily_state``
table and used by the Pattern Engine for context-aware analysis.

Usage:
    python -m src.daily_state --date 2025-01-15 --sleep 7.5 --stress 3 \\
        --physical "нормально" --notes "хороший сон, бодрость"

    # Interactive mode (no arguments):
    python -m src.daily_state
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

from src.config import DB_PATH
from src.db_writer import insert_daily_state, transaction, get_connection

logger = logging.getLogger(__name__)


def save_daily_state(
    *,
    day: str | date | None = None,
    sleep_hours: float | None = None,
    stress_level: int | None = None,
    physical_state: str | None = None,
    notes: str | None = None,
    db_path: Path | str | None = None,
) -> int:
    """
    Save or update the daily state for a trading day.

    Returns the row ID.
    """
    db = db_path or DB_PATH
    day_str = str(day or date.today())

    with transaction(db) as conn:
        row_id = insert_daily_state(
            conn,
            day=day_str,
            sleep_hours=sleep_hours,
            stress_level=stress_level,
            physical_state=physical_state,
            notes=notes,
        )

    logger.info("Daily state saved for %s (id=%d)", day_str, row_id)
    return row_id


def get_daily_state(
    day: str | date | None = None,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Fetch the daily state for a specific day."""
    db = db_path or DB_PATH
    day_str = str(day or date.today())

    conn = get_connection(db)
    try:
        row = conn.execute(
            "SELECT * FROM daily_state WHERE date = ?", (day_str,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _interactive_input() -> dict[str, Any]:
    """Collect daily state interactively from stdin."""
    print("═══ HEKTO: Состояние дня ═══\n")

    day_str = input(f"Дата [{date.today()}]: ").strip()
    if not day_str:
        day_str = str(date.today())

    sleep_str = input("Часов сна [?]: ").strip()
    sleep_hours = float(sleep_str) if sleep_str else None

    stress_str = input("Уровень стресса (1-10) [?]: ").strip()
    stress_level = None
    if stress_str:
        stress_level = max(1, min(10, int(stress_str)))

    physical_state = input("Физическое состояние [?]: ").strip() or None
    notes = input("Заметки [?]: ").strip() or None

    return {
        "day": day_str,
        "sleep_hours": sleep_hours,
        "stress_level": stress_level,
        "physical_state": physical_state,
        "notes": notes,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="HEKTO daily state — record trader's physical/mental state",
    )
    parser.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--sleep", type=float, default=None, help="Hours of sleep")
    parser.add_argument("--stress", type=int, default=None, help="Stress level 1-10")
    parser.add_argument("--physical", default=None, help="Physical state description")
    parser.add_argument("--notes", default=None, help="Free-form notes")
    parser.add_argument("--db", type=Path, default=None, help="Override DB path")
    parser.add_argument("--show", action="store_true", help="Show current state for date")
    args = parser.parse_args()

    db = args.db

    if args.show:
        state = get_daily_state(args.date, db_path=db)
        if state:
            print(f"Дата: {state['date']}")
            print(f"Сон: {state.get('sleep_hours', '?')} ч")
            print(f"Стресс: {state.get('stress_level', '?')} / 10")
            print(f"Физическое состояние: {state.get('physical_state', '—')}")
            print(f"Заметки: {state.get('notes', '—')}")
        else:
            print("Нет данных за этот день.")
        return

    # If no arguments provided, run interactive mode
    has_args = any([args.date, args.sleep, args.stress, args.physical, args.notes])

    if has_args:
        save_daily_state(
            day=args.date,
            sleep_hours=args.sleep,
            stress_level=args.stress,
            physical_state=args.physical,
            notes=args.notes,
            db_path=db,
        )
        print(f"✅ Состояние дня сохранено ({args.date or date.today()}).")
    else:
        try:
            data = _interactive_input()
            save_daily_state(db_path=db, **data)
            print(f"\n✅ Состояние дня сохранено ({data['day']}).")
        except (KeyboardInterrupt, EOFError):
            print("\nОтмена.")
            sys.exit(0)


if __name__ == "__main__":
    main()
