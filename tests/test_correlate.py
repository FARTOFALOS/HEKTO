"""
Tests for the market correlation module.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.db_writer import (
    init_db,
    insert_audio_file,
    insert_speech_chunk,
    transaction,
)
from src.correlate import ingest_candles, correlate_chunks_to_candles


@pytest.fixture()
def candle_csv(tmp_path: Path) -> Path:
    """Create a minimal candle CSV file."""
    csv_file = tmp_path / "candles.csv"
    rows = [
        {"timestamp": "2025-01-15T10:00:00", "open": "42000", "high": "42050", "low": "41990", "close": "42020", "volume": "100"},
        {"timestamp": "2025-01-15T10:01:00", "open": "42020", "high": "42080", "low": "42010", "close": "42070", "volume": "120"},
        {"timestamp": "2025-01-15T10:02:00", "open": "42070", "high": "42100", "low": "42050", "close": "42090", "volume": "90"},
        {"timestamp": "2025-01-15T10:03:00", "open": "42090", "high": "42110", "low": "42000", "close": "42010", "volume": "200"},
    ]
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_file


@pytest.fixture()
def db_with_chunks(tmp_path: Path) -> Path:
    """Create a DB with speech chunks that have spoken_time."""
    db = tmp_path / "test.db"
    init_db(db)
    with transaction(db) as conn:
        aid = insert_audio_file(conn, filename="a.wav", recorded_at="2025-01-15T10:00:00")
        insert_speech_chunk(
            conn,
            audio_file_id=aid,
            chunk_index=0,
            chunk_start_ms=0,
            chunk_end_ms=3000,
            text="test",
            spoken_time="10:01",
            system_time="10:01:05",
        )
        insert_speech_chunk(
            conn,
            audio_file_id=aid,
            chunk_index=1,
            chunk_start_ms=4000,
            chunk_end_ms=7000,
            text="test 2",
            spoken_time="10:03",
            system_time="10:03:10",
        )
    return db


class TestIngestCandles:
    def test_ingest_creates_rows(self, candle_csv: Path, tmp_path: Path) -> None:
        db = tmp_path / "test_ingest.db"
        init_db(db)
        count = ingest_candles(candle_csv, symbol="BTCUSDT", db_path=db)
        assert count == 4


class TestCorrelation:
    def test_link_chunks(self, candle_csv: Path, db_with_chunks: Path) -> None:
        # First ingest candles into the same DB
        ingest_candles(candle_csv, symbol="BTCUSDT", db_path=db_with_chunks)
        # Now correlate
        linked = correlate_chunks_to_candles("2025-01-15", symbol="BTCUSDT", db_path=db_with_chunks)
        assert linked == 2
