"""
HEKTO market correlation module.

Loads 1-minute candle data from a CSV file (or in the future from an API),
matches speech chunks to the closest candle by time, and writes the
market_context record into the DB.

CSV expected columns: timestamp, open, high, low, close, volume
(timestamp in ISO-8601 or a pandas-parseable format.)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.config import DB_PATH, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME
from src.db_writer import get_connection, insert_market_context, transaction

logger = logging.getLogger(__name__)

# ── CSV loading ───────────────────────────────────────────────────────────

def load_candles(csv_path: Path, symbol: str = DEFAULT_SYMBOL) -> pd.DataFrame:
    """
    Load 1-minute candle data from a CSV file.

    Returns a DataFrame with a datetime index and columns:
    open, high, low, close, volume.
    """
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["symbol"] = symbol
    logger.info("Loaded %d candles for %s from %s", len(df), symbol, csv_path.name)
    return df


def ingest_candles(csv_path: Path, symbol: str = DEFAULT_SYMBOL, db_path: Path | str | None = None) -> int:
    """
    Read candles from *csv_path* and insert them into the market_context table.

    Returns the number of rows inserted.
    """
    df = load_candles(csv_path, symbol)
    db = db_path or DB_PATH
    count = 0
    with transaction(db) as conn:
        for _, row in df.iterrows():
            insert_market_context(
                conn,
                timestamp=row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
                symbol=symbol,
                timeframe=DEFAULT_TIMEFRAME,
                open_=float(row["open"]) if pd.notna(row["open"]) else None,
                high=float(row["high"]) if pd.notna(row["high"]) else None,
                low=float(row["low"]) if pd.notna(row["low"]) else None,
                close=float(row["close"]) if pd.notna(row["close"]) else None,
                volume=float(row["volume"]) if pd.notna(row["volume"]) else None,
            )
            count += 1
    logger.info("Ingested %d candles into DB", count)
    return count

# ── Correlation ───────────────────────────────────────────────────────────

def correlate_chunks_to_candles(
    trading_date: str,
    symbol: str = DEFAULT_SYMBOL,
    db_path: Path | str | None = None,
) -> int:
    """
    For every speech_chunk that has a spoken_time or system_time on *trading_date*,
    find the closest 1-minute candle in market_context and set trade_context_id.

    Parameters
    ----------
    trading_date : "YYYY-MM-DD"
    symbol : market symbol
    db_path : override database path

    Returns
    -------
    Number of chunks linked.
    """
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        # Fetch candles for the date
        candles = conn.execute(
            """SELECT id, timestamp FROM market_context
               WHERE symbol = ? AND timestamp LIKE ?
               ORDER BY timestamp""",
            (symbol, f"{trading_date}%"),
        ).fetchall()

        if not candles:
            logger.warning("No candles found for %s on %s", symbol, trading_date)
            return 0

        candle_times = [
            (row["id"], datetime.fromisoformat(row["timestamp"])) for row in candles
        ]

        # Fetch chunks for the date
        chunks = conn.execute(
            """SELECT id, spoken_time, system_time FROM speech_chunks
               WHERE (spoken_time IS NOT NULL OR system_time IS NOT NULL)
                 AND trade_context_id IS NULL""",
        ).fetchall()

        linked = 0
        for chunk in chunks:
            # Prefer spoken_time; fall back to system_time
            time_str = chunk["spoken_time"] or chunk["system_time"]
            if not time_str:
                continue
            try:
                # Build a full datetime for comparison
                if len(time_str) <= 5:  # "HH:MM"
                    chunk_dt = datetime.fromisoformat(f"{trading_date}T{time_str}:00")
                else:
                    chunk_dt = datetime.fromisoformat(f"{trading_date}T{time_str}")
            except ValueError:
                continue

            # Find closest candle
            best_id, best_delta = None, timedelta.max
            for cid, cdt in candle_times:
                delta = abs(chunk_dt - cdt)
                if delta < best_delta:
                    best_id, best_delta = cid, delta

            if best_id is not None and best_delta <= timedelta(minutes=5):
                conn.execute(
                    "UPDATE speech_chunks SET trade_context_id = ? WHERE id = ?",
                    (best_id, chunk["id"]),
                )
                linked += 1

        conn.commit()
        logger.info("Linked %d chunks to candles for %s", linked, trading_date)
        return linked
    finally:
        conn.close()


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="HEKTO market correlation")
    sub = parser.add_subparsers(dest="command")

    ingest_p = sub.add_parser("ingest", help="Load candle CSV into DB")
    ingest_p.add_argument("csv", type=Path)
    ingest_p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    ingest_p.add_argument("--db", type=Path, default=None)

    link_p = sub.add_parser("link", help="Link speech chunks to candles")
    link_p.add_argument("date", help="Trading date YYYY-MM-DD")
    link_p.add_argument("--symbol", default=DEFAULT_SYMBOL)
    link_p.add_argument("--db", type=Path, default=None)

    args = parser.parse_args()

    if args.command == "ingest":
        ingest_candles(args.csv, symbol=args.symbol, db_path=args.db)
    elif args.command == "link":
        correlate_chunks_to_candles(args.date, symbol=args.symbol, db_path=args.db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
