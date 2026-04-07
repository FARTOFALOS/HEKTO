"""
Tests for the HEKTO daily state CLI (src/daily_state.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db_writer import init_db, get_connection
from src.daily_state import save_daily_state, get_daily_state


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    init_db(db)
    return db


class TestSaveDailyState:
    def test_save_state(self, db_path: Path) -> None:
        row_id = save_daily_state(
            day="2025-01-15",
            sleep_hours=7.5,
            stress_level=3,
            physical_state="нормально",
            notes="хороший сон",
            db_path=db_path,
        )
        assert row_id > 0

    def test_overwrite_state(self, db_path: Path) -> None:
        save_daily_state(day="2025-01-15", sleep_hours=7.0, db_path=db_path)
        save_daily_state(day="2025-01-15", sleep_hours=8.0, db_path=db_path)

        state = get_daily_state("2025-01-15", db_path=db_path)
        assert state is not None
        assert state["sleep_hours"] == 8.0


class TestGetDailyState:
    def test_get_existing(self, db_path: Path) -> None:
        save_daily_state(
            day="2025-01-15",
            sleep_hours=6.5,
            stress_level=5,
            physical_state="устал",
            notes="плохая ночь",
            db_path=db_path,
        )
        state = get_daily_state("2025-01-15", db_path=db_path)
        assert state is not None
        assert state["sleep_hours"] == 6.5
        assert state["stress_level"] == 5
        assert state["physical_state"] == "устал"
        assert state["notes"] == "плохая ночь"

    def test_get_nonexistent(self, db_path: Path) -> None:
        state = get_daily_state("2025-01-20", db_path=db_path)
        assert state is None

    def test_defaults_to_none(self, db_path: Path) -> None:
        save_daily_state(day="2025-01-15", db_path=db_path)
        state = get_daily_state("2025-01-15", db_path=db_path)
        assert state is not None
        assert state["sleep_hours"] is None
        assert state["stress_level"] is None
