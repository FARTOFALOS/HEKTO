"""
HEKTO daily pipeline runner.

Runs the core daily workflow in one command:
recordings → candles → correlation → trade events → chain linking → baseline → report.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from src.baseline import compute_baseline, save_baseline
from src.chain import auto_close_stale_chains, import_trades_csv, link_events_to_chains
from src.config import DB_PATH, DEFAULT_SYMBOL, PATTERNS_DIR, RAW_DIR
from src.correlate import correlate_chunks_to_candles, ingest_candles
from src.pattern_engine import generate_pattern_report, run_pattern_analysis
from src.process_recording import process_recording
from src.reporter import generate_daily_report

logger = logging.getLogger(__name__)


def discover_recordings(trading_date: str | date, raw_dir: Path | None = None) -> list[Path]:
    """Return all raw recordings for a trading date."""
    day_str = str(trading_date).replace("-", "")
    search_dir = raw_dir or RAW_DIR
    return sorted(search_dir.glob(f"recording_{day_str}_*.wav"))


def run_daily(
    trading_date: str | date | None = None,
    *,
    candles_csv: Path | None = None,
    trades_csv: Path | None = None,
    raw_dir: Path | None = None,
    db_path: Path | str | None = None,
    symbol: str = DEFAULT_SYMBOL,
    report_output_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the full daily HEKTO workflow and return a summary."""
    day = trading_date or date.today().isoformat()
    day_str = str(day)
    db = db_path or DB_PATH

    recordings = discover_recordings(day_str, raw_dir=raw_dir)
    processed_recordings = 0
    for audio_path in recordings:
        process_recording(audio_path, db_path=db)
        processed_recordings += 1

    candles_ingested = ingest_candles(candles_csv, symbol=symbol, db_path=db) if candles_csv else 0
    chunk_links = correlate_chunks_to_candles(day_str, symbol=symbol, db_path=db)
    trades_imported = import_trades_csv(trades_csv, symbol=symbol, db_path=db) if trades_csv else 0
    event_links = link_events_to_chains(day_str, db_path=db)
    stale_closed = auto_close_stale_chains(db_path=db)

    baseline = compute_baseline(target_date=day_str, db_path=db)
    baseline_saved = save_baseline(baseline, db_path=db) if baseline else None

    # Pattern Engine: run after baseline, before report
    patterns = run_pattern_analysis(db_path=db)
    pattern_report = generate_pattern_report(patterns, output_dir=report_output_dir or PATTERNS_DIR) if patterns else None

    report_path = generate_daily_report(day=day_str, db_path=db, output_dir=report_output_dir or PATTERNS_DIR)

    summary = {
        "date": day_str,
        "processed_recordings": processed_recordings,
        "candles_ingested": candles_ingested,
        "chunk_links": chunk_links,
        "trades_imported": trades_imported,
        "event_links": event_links,
        "stale_closed": stale_closed,
        "baseline_saved": baseline_saved,
        "patterns_found": len(patterns),
        "pattern_report": str(pattern_report) if pattern_report else None,
        "report_path": report_path,
    }
    logger.info("Daily run summary: %s", summary)
    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the HEKTO daily workflow")
    parser.add_argument("--date", default=None, help="Trading date YYYY-MM-DD (default: today)")
    parser.add_argument("--candles", type=Path, default=None, help="Path to candle CSV for the day")
    parser.add_argument("--trades", type=Path, default=None, help="Path to trade events CSV for the day")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR, help="Directory with raw recordings")
    parser.add_argument("--db", type=Path, default=None, help="Override SQLite DB path")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Market symbol")
    parser.add_argument("--report-dir", type=Path, default=PATTERNS_DIR, help="Directory for report output")
    args = parser.parse_args()

    summary = run_daily(
        trading_date=args.date,
        candles_csv=args.candles,
        trades_csv=args.trades,
        raw_dir=args.raw_dir,
        db_path=args.db,
        symbol=args.symbol,
        report_output_dir=args.report_dir,
    )
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
