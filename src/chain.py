"""
HEKTO trade chain manager.

Manages the lifecycle of trade chains — the central unit of the system.
A chain represents the full decision path from first analysis to outcome:

    [Analysis] → [Expectation] → [Doubt] → [Decision] → [Outcome]

Chains are opened by voice triggers or manual command, and closed by
trade events, voice triggers, or silence timeout.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import CHAIN_SILENCE_TIMEOUT_MIN, DB_PATH, DEFAULT_SYMBOL
from src.db_writer import (
    get_connection,
    insert_trade_chain,
    insert_trade_event,
    transaction,
    update_trade_chain,
)

logger = logging.getLogger(__name__)


def open_chain(
    *,
    symbol: str | None = None,
    direction: str | None = None,
    opened_at: str | None = None,
    db_path: Path | str | None = None,
) -> int:
    """
    Open a new trade chain.

    Returns the chain_id.
    """
    db = db_path or DB_PATH
    if opened_at is None:
        opened_at = datetime.now().isoformat()

    with transaction(db) as conn:
        chain_id = insert_trade_chain(
            conn,
            symbol=symbol or DEFAULT_SYMBOL,
            direction=direction,
            status="incomplete",
            opened_at=opened_at,
        )
    logger.info("Opened chain %d  symbol=%s  at=%s", chain_id, symbol, opened_at)
    return chain_id


def close_chain(
    chain_id: int,
    *,
    outcome: str | None = None,
    pnl: float | None = None,
    closed_at: str | None = None,
    db_path: Path | str | None = None,
) -> None:
    """
    Close a trade chain with outcome and optional P&L.
    """
    db = db_path or DB_PATH
    if closed_at is None:
        closed_at = datetime.now().isoformat()

    with transaction(db) as conn:
        update_trade_chain(
            conn, chain_id,
            outcome=outcome,
            pnl=pnl,
            status="complete",
            closed_at=closed_at,
        )
    logger.info("Closed chain %d  outcome=%s  pnl=%s", chain_id, outcome, pnl)


def get_active_chain(db_path: Path | str | None = None) -> dict[str, Any] | None:
    """
    Return the most recent incomplete chain, or None.
    """
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        row = conn.execute(
            """SELECT * FROM trade_chains
               WHERE status = 'incomplete'
               ORDER BY opened_at DESC LIMIT 1""",
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def link_chunk_to_chain(
    chunk_id: int,
    chain_id: int,
    db_path: Path | str | None = None,
) -> None:
    """Set chain_id on an existing speech chunk."""
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        conn.execute(
            "UPDATE speech_chunks SET chain_id = ? WHERE id = ?",
            (chain_id, chunk_id),
        )
        conn.commit()
    finally:
        conn.close()


def auto_close_stale_chains(db_path: Path | str | None = None) -> int:
    """
    Close any incomplete chain whose latest chunk is older than
    CHAIN_SILENCE_TIMEOUT_MIN minutes ago.

    Returns the number of chains closed.
    """
    db = db_path or DB_PATH
    cutoff = (datetime.now() - timedelta(minutes=CHAIN_SILENCE_TIMEOUT_MIN)).isoformat()
    conn = get_connection(db)
    try:
        # Find incomplete chains where the newest chunk is before the cutoff
        stale = conn.execute(
            """SELECT tc.id, MAX(sc.system_time) as last_time
               FROM trade_chains tc
               LEFT JOIN speech_chunks sc ON sc.chain_id = tc.id
               WHERE tc.status = 'incomplete'
               GROUP BY tc.id
               HAVING last_time IS NOT NULL AND last_time < ?""",
            (cutoff,),
        ).fetchall()

        closed = 0
        for row in stale:
            update_trade_chain(conn, row["id"], status="complete", closed_at=row["last_time"])
            closed += 1

        conn.commit()
        if closed:
            logger.info("Auto-closed %d stale chains (timeout=%d min)", closed, CHAIN_SILENCE_TIMEOUT_MIN)
        return closed
    finally:
        conn.close()


def import_trades_csv(
    csv_path: Path,
    *,
    symbol: str | None = None,
    db_path: Path | str | None = None,
) -> int:
    """
    Import trade events from a broker CSV export.

    Expected columns: timestamp, event_type, symbol, direction, price, quantity
    (event_type: 'entry' or 'exit')

    Returns count of events imported.
    """
    db = db_path or DB_PATH
    count = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        with transaction(db) as conn:
            for row in reader:
                insert_trade_event(
                    conn,
                    event_type=row.get("event_type", "entry"),
                    symbol=row.get("symbol", symbol or DEFAULT_SYMBOL),
                    direction=row.get("direction"),
                    price=float(row["price"]) if row.get("price") else None,
                    quantity=float(row["quantity"]) if row.get("quantity") else None,
                    timestamp=row.get("timestamp", ""),
                    source="csv",
                )
                count += 1
    logger.info("Imported %d trade events from %s", count, csv_path.name)
    return count


def link_events_to_chains(
    trading_date: str,
    *,
    db_path: Path | str | None = None,
) -> int:
    """
    Match unlinked trade events to chains based on temporal proximity.

    For each unlinked event on trading_date:
    - entry events: find or create a chain, link speech chunks within 3 min BEFORE
    - exit events: find the chain with matching entry, close it

    Known limitation:
    Exit events still resolve to the latest incomplete chain for the same
    symbol. If multiple same-symbol positions overlap, links can be wrong.

    Returns count of events linked.
    """
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        events = conn.execute(
            """SELECT * FROM trade_events
               WHERE chain_id IS NULL AND timestamp LIKE ?
               ORDER BY timestamp""",
            (f"{trading_date}%",),
        ).fetchall()

        linked = 0
        for ev in events:
            ev = dict(ev)
            ev_dt = datetime.fromisoformat(ev["timestamp"])

            if ev["event_type"] == "entry":
                # Find or create a chain
                chain = conn.execute(
                    """SELECT id FROM trade_chains
                       WHERE status = 'incomplete'
                         AND symbol = ?
                         AND opened_at <= ?
                       ORDER BY opened_at DESC LIMIT 1""",
                    (ev["symbol"], ev["timestamp"]),
                ).fetchone()

                if chain:
                    chain_id = chain["id"]
                else:
                    cur = conn.execute(
                        """INSERT INTO trade_chains
                           (symbol, direction, status, opened_at)
                           VALUES (?, ?, 'incomplete', ?)""",
                        (ev["symbol"], ev["direction"], ev["timestamp"]),
                    )
                    chain_id = cur.lastrowid

                conn.execute(
                    "UPDATE trade_events SET chain_id = ? WHERE id = ?",
                    (chain_id, ev["id"]),
                )
                if ev.get("direction"):
                    conn.execute(
                        "UPDATE trade_chains SET direction = ? WHERE id = ?",
                        (ev["direction"], chain_id),
                    )

                # Link speech chunks within 3 min before entry (same day only)
                window_start = (ev_dt - timedelta(minutes=3)).strftime("%H:%M:%S")
                window_end = ev_dt.strftime("%H:%M:%S")
                conn.execute(
                    """UPDATE speech_chunks
                       SET chain_id = ?
                       WHERE chain_id IS NULL
                         AND system_time BETWEEN ? AND ?
                         AND audio_file_id IN (
                             SELECT id FROM audio_files WHERE recorded_at LIKE ?
                         )""",
                    (chain_id, window_start, window_end, f"{trading_date}%"),
                )
                linked += 1

            elif ev["event_type"] == "exit":
                # Find matching chain.
                matching_chains = conn.execute(
                    """SELECT id FROM trade_chains
                       WHERE status = 'incomplete'
                          AND symbol = ?
                        ORDER BY opened_at DESC""",
                    (ev["symbol"],),
                ).fetchall()

                if len(matching_chains) > 1:
                    logger.warning(
                        "Known limitation: exit event %s matched to latest incomplete chain for %s; concurrent same-symbol positions may link incorrectly",
                        ev["id"],
                        ev["symbol"],
                    )

                chain = matching_chains[0] if matching_chains else None

                if chain:
                    chain_id = chain["id"]
                    conn.execute(
                        "UPDATE trade_events SET chain_id = ? WHERE id = ?",
                        (chain_id, ev["id"]),
                    )

                    # Determine outcome from entry/exit prices
                    entry_ev = conn.execute(
                        """SELECT price, direction FROM trade_events
                           WHERE chain_id = ? AND event_type = 'entry'
                           ORDER BY timestamp LIMIT 1""",
                        (chain_id,),
                    ).fetchone()

                    outcome = None
                    pnl = None
                    if entry_ev and entry_ev["price"] and ev["price"]:
                        entry_price = float(entry_ev["price"])
                        exit_price = float(ev["price"])
                        direction = entry_ev["direction"]
                        if direction == "long":
                            pnl = exit_price - entry_price
                        elif direction == "short":
                            pnl = entry_price - exit_price
                        if pnl is not None:
                            if pnl > 0:
                                outcome = "profit"
                            elif pnl < 0:
                                outcome = "loss"
                            else:
                                outcome = "breakeven"

                    update_trade_chain(
                        conn, chain_id,
                        outcome=outcome,
                        pnl=pnl,
                        status="complete",
                        closed_at=ev["timestamp"],
                    )

                    # Link speech chunks AFTER entry to this chain (same day only)
                    conn.execute(
                        """UPDATE speech_chunks
                           SET chain_id = ?
                           WHERE chain_id IS NULL
                             AND system_time <= ?
                             AND audio_file_id IN (
                                 SELECT id FROM audio_files WHERE recorded_at LIKE ?
                             )""",
                        (chain_id, ev_dt.strftime("%H:%M:%S"), f"{trading_date}%"),
                    )
                    linked += 1

        conn.commit()
        logger.info("Linked %d trade events to chains on %s", linked, trading_date)
        return linked
    finally:
        conn.close()


def get_chain_summary(
    chain_id: int,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """Return a summary of a chain with its chunks and events."""
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        chain = conn.execute(
            "SELECT * FROM trade_chains WHERE id = ?", (chain_id,)
        ).fetchone()
        if not chain:
            return None

        chunks = conn.execute(
            """SELECT id, chunk_role, text, system_time, voice_features, baseline_deviation
               FROM speech_chunks WHERE chain_id = ?
               ORDER BY chunk_start_ms""",
            (chain_id,),
        ).fetchall()

        events = conn.execute(
            """SELECT * FROM trade_events WHERE chain_id = ?
               ORDER BY timestamp""",
            (chain_id,),
        ).fetchall()

        return {
            "chain": dict(chain),
            "chunks": [dict(c) for c in chunks],
            "events": [dict(e) for e in events],
        }
    finally:
        conn.close()
