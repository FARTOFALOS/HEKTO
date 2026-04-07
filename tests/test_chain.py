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


class TestLinkEventsToChains:
    """Tests for link_events_to_chains with parallel positions."""

    def test_simple_entry_exit(self, db_path: Path) -> None:
        """Single entry/exit pair creates one chain."""
        with transaction(db_path) as conn:
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=42000.0, timestamp="2025-01-15T10:05:00",
            )
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", price=42500.0, timestamp="2025-01-15T10:30:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 2

        conn = get_connection(db_path)
        chains = conn.execute("SELECT * FROM trade_chains ORDER BY opened_at").fetchall()
        conn.close()
        assert len(chains) == 1
        assert chains[0]["status"] == "complete"
        assert chains[0]["outcome"] == "profit"
        assert chains[0]["pnl"] == 500.0

    def test_parallel_same_symbol_price_matching(self, db_path: Path) -> None:
        """Two overlapping positions in the same symbol: exits matched by price."""
        with transaction(db_path) as conn:
            # Position A: entry at 42000
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=42000.0, timestamp="2025-01-15T10:00:00",
            )
            # Position B: entry at 43000
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=43000.0, timestamp="2025-01-15T10:05:00",
            )
            # Exit B at 43200 (closest to 43000 entry)
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", price=43200.0, timestamp="2025-01-15T10:20:00",
            )
            # Exit A at 42100 (closest to 42000 entry)
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", price=42100.0, timestamp="2025-01-15T10:25:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 4

        conn = get_connection(db_path)
        chains = conn.execute(
            "SELECT * FROM trade_chains ORDER BY opened_at",
        ).fetchall()
        conn.close()

        assert len(chains) == 2
        # Chain A: entry 42000 → exit 42100 = +100
        assert chains[0]["pnl"] == pytest.approx(100.0)
        assert chains[0]["status"] == "complete"
        # Chain B: entry 43000 → exit 43200 = +200
        assert chains[1]["pnl"] == pytest.approx(200.0)
        assert chains[1]["status"] == "complete"

    def test_parallel_different_symbols(self, db_path: Path) -> None:
        """Parallel positions in different symbols are always separate chains."""
        with transaction(db_path) as conn:
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=42000.0, timestamp="2025-01-15T10:00:00",
            )
            insert_trade_event(
                conn, event_type="entry", symbol="ETHUSDT",
                direction="short", price=3000.0, timestamp="2025-01-15T10:02:00",
            )
            insert_trade_event(
                conn, event_type="exit", symbol="ETHUSDT",
                direction="short", price=2900.0, timestamp="2025-01-15T10:15:00",
            )
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", price=42500.0, timestamp="2025-01-15T10:20:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 4

        conn = get_connection(db_path)
        chains = conn.execute("SELECT * FROM trade_chains ORDER BY opened_at").fetchall()
        conn.close()

        assert len(chains) == 2
        btc_chain = [c for c in chains if c["symbol"] == "BTCUSDT"][0]
        eth_chain = [c for c in chains if c["symbol"] == "ETHUSDT"][0]
        assert btc_chain["pnl"] == pytest.approx(500.0)
        assert eth_chain["pnl"] == pytest.approx(100.0)  # short: 3000 - 2900

    def test_entry_creates_new_chain_always(self, db_path: Path) -> None:
        """Each entry event creates a separate chain (no reuse)."""
        with transaction(db_path) as conn:
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=42000.0, timestamp="2025-01-15T10:00:00",
            )
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=43000.0, timestamp="2025-01-15T10:05:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 2

        conn = get_connection(db_path)
        chains = conn.execute("SELECT * FROM trade_chains").fetchall()
        conn.close()
        assert len(chains) == 2

    def test_exit_without_matching_chain(self, db_path: Path) -> None:
        """Exit event with no matching chain is skipped (not linked)."""
        with transaction(db_path) as conn:
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", price=42500.0, timestamp="2025-01-15T10:30:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 0

    def test_speech_chunks_linked_to_correct_chain(self, db_path: Path) -> None:
        """Speech chunks between entry and exit are linked to the correct chain."""
        with transaction(db_path) as conn:
            aid = insert_audio_file(
                conn, filename="a.wav", recorded_at="2025-01-15T09:00:00",
            )
            # Chunk at 10:03 — before entry A
            insert_speech_chunk(
                conn, audio_file_id=aid, chunk_index=0,
                chunk_start_ms=0, chunk_end_ms=3000,
                text="вижу сетап", system_time="10:03:00",
            )
            # Chunk at 10:12 — between entries
            insert_speech_chunk(
                conn, audio_file_id=aid, chunk_index=1,
                chunk_start_ms=3000, chunk_end_ms=6000,
                text="думаю пойдёт", system_time="10:12:00",
            )
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=42000.0, timestamp="2025-01-15T10:05:00",
            )
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", price=42500.0, timestamp="2025-01-15T10:30:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 2

        conn = get_connection(db_path)
        chunks = conn.execute(
            "SELECT id, chain_id, system_time FROM speech_chunks ORDER BY system_time",
        ).fetchall()
        conn.close()

        # Chunk at 10:03 is within 3 min before entry (10:05) → linked
        assert chunks[0]["chain_id"] is not None
        # Chunk at 10:12 is between entry and exit → linked to same chain
        assert chunks[1]["chain_id"] == chunks[0]["chain_id"]

    def test_fifo_fallback_when_no_prices(self, db_path: Path) -> None:
        """When exit has no price, fall back to FIFO (oldest chain first)."""
        with transaction(db_path) as conn:
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=42000.0, timestamp="2025-01-15T10:00:00",
            )
            insert_trade_event(
                conn, event_type="entry", symbol="BTCUSDT",
                direction="long", price=43000.0, timestamp="2025-01-15T10:05:00",
            )
            # Exit without price
            insert_trade_event(
                conn, event_type="exit", symbol="BTCUSDT",
                direction="long", timestamp="2025-01-15T10:20:00",
            )

        linked = link_events_to_chains("2025-01-15", db_path=db_path)
        assert linked == 3

        conn = get_connection(db_path)
        chains = conn.execute("SELECT * FROM trade_chains ORDER BY opened_at").fetchall()
        conn.close()

        # First chain (FIFO) should be closed
        assert chains[0]["status"] == "complete"
        # Second chain should still be open
        assert chains[1]["status"] == "incomplete"
