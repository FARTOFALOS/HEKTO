"""
Tests for the reporter module.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db_writer import (
    init_db,
    insert_audio_file,
    insert_daily_state,
    insert_speech_chunk,
    transaction,
)
from src.reporter import generate_daily_report


@pytest.fixture()
def populated_db(tmp_path: Path) -> Path:
    """Create a DB with sample data for a single day."""
    db = tmp_path / "test.db"
    init_db(db)

    with transaction(db) as conn:
        aid = insert_audio_file(
            conn,
            filename="recording_20250115_100000.wav",
            recorded_at="2025-01-15T10:00:00",
            duration_sec=300.0,
            sample_rate=16000,
            silence_threshold_db=-54.0,
            mean_db=-40.0,
        )
        insert_speech_chunk(
            conn,
            audio_file_id=aid,
            chunk_index=0,
            chunk_start_ms=0,
            chunk_end_ms=5000,
            text="рынок идёт вверх",
            spoken_time="10:01",
            system_time="10:01:12",
            time_confidence=0.95,
            voice_features='{"speech_rate_proxy": 3.5, "pitch_mean_hz": 130.0, "pitch_std_hz": 12.0, "energy_mean_db": -20.0, "energy_std_db": 5.0, "pause_ratio": 0.1, "duration_sec": 5.0}',
        )
        insert_speech_chunk(
            conn,
            audio_file_id=aid,
            chunk_index=1,
            chunk_start_ms=6000,
            chunk_end_ms=12000,
            text="я знаю что не стоит но войду",
            system_time="10:03:00",
            time_confidence=0.0,
            self_catch_flag=True,
            voice_features='{"speech_rate_proxy": 5.0, "pitch_mean_hz": 155.0, "pitch_std_hz": 20.0, "energy_mean_db": -15.0, "energy_std_db": 8.0, "pause_ratio": 0.02, "duration_sec": 6.0}',
        )
        insert_daily_state(
            conn,
            day="2025-01-15",
            sleep_hours=6.0,
            stress_level=6,
            physical_state="нормальное",
            notes="плохо спал",
        )

    return db


class TestReporter:
    def test_report_is_generated(self, populated_db: Path, tmp_path: Path) -> None:
        # Monkey-patch PATTERNS_DIR to tmp
        import src.reporter as rep
        original = rep.PATTERNS_DIR
        rep.PATTERNS_DIR = tmp_path
        try:
            report_path = generate_daily_report(day="2025-01-15", db_path=populated_db)
            assert report_path.exists()
            content = report_path.read_text(encoding="utf-8")
            assert "2025-01-15" in content
            assert "рынок идёт вверх" in content
            assert "SELF_CATCH" in content
        finally:
            rep.PATTERNS_DIR = original

    def test_report_empty_day(self, populated_db: Path, tmp_path: Path) -> None:
        import src.reporter as rep
        original = rep.PATTERNS_DIR
        rep.PATTERNS_DIR = tmp_path
        try:
            report_path = generate_daily_report(day="2025-01-20", db_path=populated_db)
            content = report_path.read_text(encoding="utf-8")
            assert "Нет данных" in content
        finally:
            rep.PATTERNS_DIR = original
