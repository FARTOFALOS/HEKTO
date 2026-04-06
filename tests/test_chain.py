"""
Tests for the HEKTO trade chain manager (src/chain.py).
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.db_writer import (
    init_db,
    insert_audio_file,
    insert_speech_chunk,
    insert_trade_chain,
    insert_trade_event,
    transaction,
    get_connection,
)
from src.chain import (
    close_chain,
    get_active_chain,
    get_chain_summary,
    import_trades_csv,
    link_chunk_to_chain,
    link_events_to_chains,
    open_chain,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    init_db(db)
    return db


class TestChainLifecycle:
    def test_open_chain(self, db_path: Path) -> None:
        chain_id = open_chain(
            symbol="BTCUSDT",
            direction="long",
            opened_at="2025-01-15T10:00:00",
            db_path=db_path,
        )
        assert chain_id > 0

    def test_close_chain(self, db_path: Path) -> None:
        chain_id = open_chain(symbol="BTCUSDT", db_path=db_path)
        close_chain(chain_id, outcome="profit", pnl=150.0, db_path=db_path)

        conn = get_connection(db_path)
        row = conn.execute("SELECT * FROM trade_chains WHERE id = ?", (chain_id,)).fetchone()
        conn.close()
        assert row["status"] == "complete"
        assert row["outcome"] == "profit"
        assert row["pnl"] == 150.0

    def test_get_active_chain(self, db_path: Path) -> None:
        assert get_active_chain(db_path=db_path) is None

        chain_id = open_chain(symbol="BTCUSDT", db_path=db_path)
        active = get_active_chain(db_path=db_path)
        assert active is not None
        assert active["id"] == chain_id

    def test_get_active_chain_not_closed(self, db_path: Path) -> None:
        chain_id = open_chain(symbol="BTCUSDT", db_path=db_path)
        close_chain(chain_id, outcome="loss", db_path=db_path)

        assert get_active_chain(db_path=db_path) is None


class TestChainChunkLinking:
    def test_link_chunk_to_chain(self, db_path: Path) -> None:
        chain_id = open_chain(symbol="BTCUSDT", db_path=db_path)
        with transaction(db_path) as conn:
            aid = insert_audio_file(conn, filename="a.wav", recorded_at="2025-01-15T10:00:00")
            cid = insert_speech_chunk(
                conn, audio_file_id=aid, chunk_index=0,
                chunk_start_ms=0, chunk_end_ms=3000, text="тест",
            )
        link_chunk_to_chain(cid, chain_id, db_path=db_path)

        conn = get_connection(db_path)
        row = conn.execute("SELECT chain_id FROM speech_chunks WHERE id = ?", (cid,)).fetchone()
        conn.close()
        assert row["chain_id"] == chain_id


class TestChainSummary:
    def test_get_chain_summary(self, db_path: Path) -> None:
        chain_id = open_chain(symbol="BTCUSDT", db_path=db_path)
        with transaction(db_path) as conn:
            aid = insert_audio_file(conn, filename="a.wav", recorded_at="2025-01-15T10:00:00")
            insert_speech_chunk(
                conn, audio_file_id=aid, chunk_index=0,
                chunk_start_ms=0, chunk_end_ms=3000,
                text="вижу сетап", chunk_role="analysis", chain_id=chain_id,
            )
            insert_speech_chunk(
                conn, audio_file_id=aid, chunk_index=1,
                chunk_start_ms=3000, chunk_end_ms=6000,
                text="закрыл", chunk_role="exit", chain_id=chain_id,
            )

        summary = get_chain_summary(chain_id, db_path=db_path)
        assert summary is not None
        assert len(summary["chunks"]) == 2
        assert summary["chain"]["id"] == chain_id

    def test_nonexistent_chain(self, db_path: Path) -> None:
        assert get_chain_summary(999, db_path=db_path) is None


class TestTradeImport:
    def test_import_trades_csv(self, db_path: Path, tmp_path: Path) -> None:
        csv_file = tmp_path / "trades.csv"
        rows = [
            {"timestamp": "2025-01-15T10:05:00", "event_type": "entry", "symbol": "BTCUSDT", "direction": "long", "price": "42000", "quantity": "1"},
            {"timestamp": "2025-01-15T10:30:00", "event_type": "exit", "symbol": "BTCUSDT", "direction": "long", "price": "42500", "quantity": "1"},
        ]
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "event_type", "symbol", "direction", "price", "quantity"])
            writer.writeheader()
            writer.writerows(rows)

        count = import_trades_csv(csv_file, db_path=db_path)
        assert count == 2

        conn = get_connection(db_path)
        events = conn.execute("SELECT * FROM trade_events ORDER BY timestamp").fetchall()
        conn.close()
        assert len(events) == 2
        assert events[0]["event_type"] == "entry"
        assert events[1]["event_type"] == "exit"
