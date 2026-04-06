"""
Tests for the HEKTO database layer (db_writer).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.db_writer import (
    get_connection,
    init_db,
    insert_audio_file,
    insert_daily_state,
    insert_market_context,
    insert_pattern,
    insert_self_catch_link,
    insert_speech_chunk,
    insert_trade_chain,
    insert_trade_event,
    insert_voice_baseline,
    update_trade_chain,
    transaction,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Provide a fresh temporary database."""
    p = tmp_path / "test.db"
    init_db(p)
    return p


class TestSchema:
    def test_tables_exist(self, db_path: Path) -> None:
        conn = get_connection(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        expected = {
            "audio_files",
            "speech_chunks",
            "market_context",
            "daily_state",
            "self_catch_links",
            "patterns",
            "trade_chains",
            "trade_events",
            "voice_baseline",
        }
        assert expected.issubset(tables)

    def test_init_is_idempotent(self, db_path: Path) -> None:
        # Calling init_db twice should not raise
        init_db(db_path)
        init_db(db_path)


class TestInserts:
    def test_insert_audio_file(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            aid = insert_audio_file(
                conn,
                filename="test.wav",
                recorded_at="2025-01-15T10:00:00",
                duration_sec=120.0,
                sample_rate=16000,
                silence_threshold_db=-54.0,
                mean_db=-40.0,
            )
        assert aid is not None and aid > 0

    def test_insert_speech_chunk(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            aid = insert_audio_file(conn, filename="a.wav", recorded_at="2025-01-15T10:00:00")
            cid = insert_speech_chunk(
                conn,
                audio_file_id=aid,
                chunk_index=0,
                chunk_start_ms=0,
                chunk_end_ms=5000,
                text="тест",
                spoken_time="10:14",
                system_time="10:14:23",
                time_confidence=0.95,
                voice_features={"pitch_mean_hz": 120.0},
            )
        assert cid is not None and cid > 0

    def test_insert_market_context(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            mid = insert_market_context(
                conn,
                timestamp="2025-01-15T10:14:00",
                symbol="BTCUSDT",
                open_=42000.0,
                high=42050.0,
                low=41990.0,
                close=42020.0,
                volume=123.4,
            )
        assert mid is not None and mid > 0

    def test_insert_daily_state(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            did = insert_daily_state(
                conn,
                day="2025-01-15",
                sleep_hours=7.0,
                stress_level=4,
                physical_state="нормальное",
                notes="немного устал",
            )
        assert did is not None and did > 0

    def test_insert_pattern(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            pid = insert_pattern(
                conn,
                title="Ускорение темпа перед убытком",
                description="Темп речи растёт на 40% за 2 мин до входа",
                evidence_count=5,
                confidence=0.7,
            )
        assert pid is not None and pid > 0

    def test_insert_self_catch_link(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            aid = insert_audio_file(conn, filename="b.wav", recorded_at="2025-01-15T10:00:00")
            c1 = insert_speech_chunk(conn, audio_file_id=aid, chunk_index=0, chunk_start_ms=0, chunk_end_ms=3000, self_catch_flag=True)
            c2 = insert_speech_chunk(conn, audio_file_id=aid, chunk_index=1, chunk_start_ms=3000, chunk_end_ms=6000)
            lid = insert_self_catch_link(conn, self_catch_event_id=c1, emotion_event_id=c2, time_delta_seconds=5.0, same_trade=True)
        assert lid is not None and lid > 0


class TestTransaction:
    def test_rollback_on_error(self, db_path: Path) -> None:
        try:
            with transaction(db_path) as conn:
                insert_audio_file(conn, filename="fail.wav", recorded_at="2025-01-15T10:00:00")
                raise ValueError("force rollback")
        except ValueError:
            pass

        conn2 = get_connection(db_path)
        count = conn2.execute("SELECT COUNT(*) FROM audio_files WHERE filename='fail.wav'").fetchone()[0]
        conn2.close()
        assert count == 0


class TestNewInserts:
    """Tests for v2 insert functions (trade_chains, trade_events, voice_baseline)."""

    def test_insert_trade_chain(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            cid = insert_trade_chain(
                conn,
                symbol="BTCUSDT",
                direction="long",
                status="incomplete",
                opened_at="2025-01-15T10:00:00",
            )
        assert cid is not None and cid > 0

    def test_update_trade_chain(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            cid = insert_trade_chain(conn, symbol="BTCUSDT", status="incomplete")
            update_trade_chain(conn, cid, outcome="profit", pnl=100.0, status="complete")

        conn2 = get_connection(db_path)
        row = conn2.execute("SELECT * FROM trade_chains WHERE id = ?", (cid,)).fetchone()
        conn2.close()
        assert row["outcome"] == "profit"
        assert row["pnl"] == 100.0
        assert row["status"] == "complete"

    def test_insert_trade_event(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            eid = insert_trade_event(
                conn,
                event_type="entry",
                symbol="BTCUSDT",
                direction="long",
                price=42000.0,
                quantity=1.0,
                timestamp="2025-01-15T10:05:00",
                source="csv",
            )
        assert eid is not None and eid > 0

    def test_insert_voice_baseline(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            bid = insert_voice_baseline(
                conn,
                day="2025-01-15",
                chunk_count=50,
                pitch_mean=130.0,
                pitch_std=15.0,
                speech_rate_mean=3.5,
                speech_rate_std=0.5,
                energy_mean=-22.0,
                energy_std=4.0,
                pause_ratio_mean=0.08,
                pause_ratio_std=0.03,
            )
        assert bid is not None and bid > 0

    def test_insert_speech_chunk_with_new_fields(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            cid = insert_trade_chain(conn, symbol="BTCUSDT", status="incomplete")
            aid = insert_audio_file(conn, filename="a.wav", recorded_at="2025-01-15T10:00:00")
            sid = insert_speech_chunk(
                conn,
                audio_file_id=aid,
                chunk_index=0,
                chunk_start_ms=0,
                chunk_end_ms=5000,
                text="вижу сетап",
                chunk_role="analysis",
                chain_id=cid,
                baseline_deviation={"pitch_deviation_pct": 25.0},
                voice_features={"pitch_mean_hz": 150.0},
            )
        assert sid is not None and sid > 0

        conn2 = get_connection(db_path)
        row = conn2.execute("SELECT * FROM speech_chunks WHERE id = ?", (sid,)).fetchone()
        conn2.close()
        assert row["chunk_role"] == "analysis"
        assert row["chain_id"] == cid
        assert row["baseline_deviation"] is not None

    def test_insert_pattern_with_new_fields(self, db_path: Path) -> None:
        with transaction(db_path) as conn:
            pid = insert_pattern(
                conn,
                title="Hold pattern before loss",
                description="When trader says 'hold' 71% chance of loss",
                conditions={"keywords": ["подержу"]},
                evidence=[1, 2, 3],
                counter_evidence=[4],
                evidence_count=3,
                counter_evidence_count=1,
                confidence=0.71,
                confidence_level="medium",
            )
        assert pid is not None and pid > 0
