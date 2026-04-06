"""
Tests for the HEKTO voice baseline engine (src/baseline.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.db_writer import (
    init_db,
    insert_audio_file,
    insert_speech_chunk,
    insert_voice_baseline,
    transaction,
)
from src.baseline import compute_baseline, compute_deviation, get_latest_baseline, save_baseline


@pytest.fixture()
def db_with_features(tmp_path: Path) -> Path:
    """Create a DB with enough chunks to form a baseline."""
    db = tmp_path / "test.db"
    init_db(db)
    with transaction(db) as conn:
        aid = insert_audio_file(conn, filename="a.wav", recorded_at="2025-01-10T10:00:00")
        # Insert 10 chunks with varying features
        for i in range(10):
            insert_speech_chunk(
                conn,
                audio_file_id=aid,
                chunk_index=i,
                chunk_start_ms=i * 5000,
                chunk_end_ms=(i + 1) * 5000,
                text=f"chunk {i}",
                system_time=f"10:{i:02d}:00",
                voice_features={
                    "pitch_mean_hz": 120.0 + i * 2,
                    "speech_rate_proxy": 3.0 + i * 0.1,
                    "energy_mean_db": -25.0 + i * 0.5,
                    "pause_ratio": 0.1 + i * 0.01,
                },
            )
    return db


class TestComputeBaseline:
    def test_baseline_computed(self, db_with_features: Path) -> None:
        result = compute_baseline(target_date="2025-01-15", db_path=db_with_features)
        assert result is not None
        assert result["chunk_count"] == 10
        assert result["pitch_mean_hz_mean"] is not None
        assert result["speech_rate_proxy_mean"] is not None

    def test_baseline_insufficient_data(self, tmp_path: Path) -> None:
        db = tmp_path / "empty.db"
        init_db(db)
        result = compute_baseline(target_date="2025-01-15", db_path=db)
        assert result is None

    def test_baseline_excludes_future_data(self, db_with_features: Path) -> None:
        # Asking for baseline on a date BEFORE the data → should return None (no data before that)
        result = compute_baseline(target_date="2025-01-09", db_path=db_with_features)
        assert result is None


class TestSaveBaseline:
    def test_save_and_retrieve(self, db_with_features: Path) -> None:
        baseline = compute_baseline(target_date="2025-01-15", db_path=db_with_features)
        assert baseline is not None

        row_id = save_baseline(baseline, db_path=db_with_features)
        assert row_id > 0

        retrieved = get_latest_baseline(target_date="2025-01-15", db_path=db_with_features)
        assert retrieved is not None
        assert retrieved["date"] == "2025-01-15"


class TestComputeDeviation:
    def test_deviation_calculation(self) -> None:
        features = {
            "pitch_mean_hz": 150.0,
            "speech_rate_proxy": 4.0,
            "energy_mean_db": -20.0,
            "pause_ratio": 0.05,
        }
        baseline = {
            "pitch_mean": 120.0,
            "pitch_std": 10.0,
            "speech_rate_mean": 3.5,
            "speech_rate_std": 0.5,
            "energy_mean": -25.0,
            "energy_std": 3.0,
            "pause_ratio_mean": 0.10,
            "pause_ratio_std": 0.02,
        }
        dev = compute_deviation(features, baseline)

        # Pitch: (150 - 120) / 120 * 100 = 25%
        assert dev["pitch_deviation_pct"] == 25.0
        # Z-score: (150 - 120) / 10 = 3.0
        assert dev["pitch_z_score"] == 3.0

        # Speech rate: (4.0 - 3.5) / 3.5 * 100 ≈ 14.3%
        assert dev["speech_rate_deviation_pct"] == pytest.approx(14.3, abs=0.1)

        # Pause ratio: (0.05 - 0.10) / 0.10 * 100 = -50%
        assert dev["pause_ratio_deviation_pct"] == -50.0

    def test_deviation_with_none_values(self) -> None:
        features = {"pitch_mean_hz": 150.0}
        baseline = {"pitch_mean": None, "pitch_std": None}
        dev = compute_deviation(features, baseline)
        assert dev["pitch_deviation_pct"] is None
