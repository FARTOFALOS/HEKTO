"""
HEKTO database schema and writer.

Manages the SQLite database: creates tables on first run, provides helper
functions to insert rows into every entity the MVP needs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator

from src.config import DB_PATH

logger = logging.getLogger(__name__)

# ── Schema DDL ────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audio_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT    NOT NULL,
    recorded_at     TEXT    NOT NULL,           -- ISO-8601
    duration_sec    REAL,
    sample_rate     INTEGER,
    silence_threshold_db REAL,                  -- dynamic threshold used
    mean_db         REAL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_chains (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT,
    direction       TEXT,                       -- long | short | NULL
    outcome         TEXT,                       -- profit | loss | breakeven | no_entry | stop | NULL
    pnl             REAL,
    status          TEXT    NOT NULL DEFAULT 'incomplete',  -- incomplete | complete
    opened_at       TEXT,                       -- ISO-8601 when chain started
    closed_at       TEXT,                       -- ISO-8601 when chain ended
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS speech_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    audio_file_id   INTEGER NOT NULL REFERENCES audio_files(id),
    chunk_index     INTEGER NOT NULL,
    chunk_start_ms  INTEGER NOT NULL,
    chunk_end_ms    INTEGER NOT NULL,
    text            TEXT,
    spoken_time     TEXT,                       -- time the trader said aloud
    system_time     TEXT,                       -- real wall-clock time
    time_confidence REAL    DEFAULT 0.0,
    voice_features  TEXT,                       -- JSON blob (raw features)
    baseline_deviation TEXT,                    -- JSON blob (deviations from baseline)
    chunk_role      TEXT    DEFAULT 'other',    -- analysis|expectation|doubt|hold|exit|reflection|other
    chain_id        INTEGER REFERENCES trade_chains(id),
    emotion         TEXT,
    self_catch_flag INTEGER DEFAULT 0,
    trade_context_id INTEGER REFERENCES market_context(id),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS market_context (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,           -- candle open time ISO-8601
    symbol          TEXT    NOT NULL,
    timeframe       TEXT    NOT NULL DEFAULT '1m',
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume          REAL,
    volatility      REAL,
    atr             REAL,
    trend           TEXT,                       -- up | down | flat
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trade_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    chain_id        INTEGER REFERENCES trade_chains(id),
    event_type      TEXT    NOT NULL,           -- entry | exit
    symbol          TEXT,
    direction       TEXT,                       -- long | short
    price           REAL,
    quantity         REAL,
    timestamp       TEXT    NOT NULL,           -- ISO-8601
    source          TEXT    DEFAULT 'csv',      -- csv | voice | manual
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS daily_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL UNIQUE,    -- YYYY-MM-DD
    sleep_hours     REAL,
    stress_level    INTEGER,                    -- 1-10
    physical_state  TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS voice_baseline (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT    NOT NULL UNIQUE,    -- YYYY-MM-DD (baseline computed for this day)
    chunk_count     INTEGER DEFAULT 0,
    pitch_mean      REAL,
    pitch_std       REAL,
    speech_rate_mean REAL,
    speech_rate_std REAL,
    energy_mean     REAL,
    energy_std      REAL,
    pause_ratio_mean REAL,
    pause_ratio_std REAL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS self_catch_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    self_catch_event_id INTEGER NOT NULL REFERENCES speech_chunks(id),
    emotion_event_id    INTEGER REFERENCES speech_chunks(id),
    time_delta_seconds  REAL,
    same_trade          INTEGER DEFAULT 0,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS patterns (
    pattern_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    description     TEXT,
    conditions      TEXT,                       -- JSON: what triggers this pattern
    evidence        TEXT,                       -- JSON: list of supporting chain_ids
    counter_evidence TEXT,                      -- JSON: list of contradicting chain_ids
    evidence_count  INTEGER DEFAULT 0,
    counter_evidence_count INTEGER DEFAULT 0,
    confidence      REAL    DEFAULT 0.0,        -- 0.0-1.0
    confidence_level TEXT   DEFAULT 'low',      -- low | medium | high
    status          TEXT    DEFAULT 'candidate', -- candidate | confirmed | rejected
    last_updated    TEXT    NOT NULL DEFAULT (datetime('now')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_audio ON speech_chunks(audio_file_id);
CREATE INDEX IF NOT EXISTS idx_chunks_self_catch ON speech_chunks(self_catch_flag);
CREATE INDEX IF NOT EXISTS idx_chunks_chain ON speech_chunks(chain_id);
CREATE INDEX IF NOT EXISTS idx_chunks_role ON speech_chunks(chunk_role);
CREATE INDEX IF NOT EXISTS idx_market_ts ON market_context(timestamp, symbol);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_state(date);
CREATE INDEX IF NOT EXISTS idx_chains_status ON trade_chains(status);
CREATE INDEX IF NOT EXISTS idx_chains_outcome ON trade_chains(outcome);
CREATE INDEX IF NOT EXISTS idx_trade_events_chain ON trade_events(chain_id);
CREATE INDEX IF NOT EXISTS idx_baseline_date ON voice_baseline(date);
"""

# ── Connection helpers ────────────────────────────────────────────────────

def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a new SQLite connection with WAL mode enabled."""
    path = str(db_path or DB_PATH)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that commits on success and rolls back on error."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Create all tables if they don't exist yet."""
    with transaction(db_path) as conn:
        conn.executescript(_SCHEMA_SQL)
    logger.info("Database initialised at %s", db_path or DB_PATH)

# ── Insert helpers ────────────────────────────────────────────────────────

def insert_audio_file(
    conn: sqlite3.Connection,
    *,
    filename: str,
    recorded_at: str,
    duration_sec: float | None = None,
    sample_rate: int | None = None,
    silence_threshold_db: float | None = None,
    mean_db: float | None = None,
) -> int:
    """Insert an audio_files row and return the new id."""
    cur = conn.execute(
        """INSERT INTO audio_files
           (filename, recorded_at, duration_sec, sample_rate, silence_threshold_db, mean_db)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (filename, recorded_at, duration_sec, sample_rate, silence_threshold_db, mean_db),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_speech_chunk(
    conn: sqlite3.Connection,
    *,
    audio_file_id: int,
    chunk_index: int,
    chunk_start_ms: int,
    chunk_end_ms: int,
    text: str | None = None,
    spoken_time: str | None = None,
    system_time: str | None = None,
    time_confidence: float = 0.0,
    voice_features: dict[str, Any] | None = None,
    baseline_deviation: dict[str, Any] | None = None,
    chunk_role: str = "other",
    chain_id: int | None = None,
    emotion: str | None = None,
    self_catch_flag: bool = False,
    trade_context_id: int | None = None,
) -> int:
    """Insert a speech_chunks row and return the new id."""
    def _json(val: dict | str | None) -> str | None:
        if val is None:
            return None
        return val if isinstance(val, str) else json.dumps(val)

    cur = conn.execute(
        """INSERT INTO speech_chunks
           (audio_file_id, chunk_index, chunk_start_ms, chunk_end_ms,
            text, spoken_time, system_time, time_confidence,
            voice_features, baseline_deviation, chunk_role, chain_id,
            emotion, self_catch_flag, trade_context_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            audio_file_id, chunk_index, chunk_start_ms, chunk_end_ms,
            text, spoken_time, system_time, time_confidence,
            _json(voice_features), _json(baseline_deviation),
            chunk_role, chain_id,
            emotion, int(self_catch_flag), trade_context_id,
        ),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_market_context(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    symbol: str,
    timeframe: str = "1m",
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    volume: float | None = None,
    volatility: float | None = None,
    atr: float | None = None,
    trend: str | None = None,
) -> int:
    cur = conn.execute(
        """INSERT INTO market_context
           (timestamp, symbol, timeframe, open, high, low, close, volume, volatility, atr, trend)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, symbol, timeframe, open_, high, low, close, volume, volatility, atr, trend),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_daily_state(
    conn: sqlite3.Connection,
    *,
    day: str | date,
    sleep_hours: float | None = None,
    stress_level: int | None = None,
    physical_state: str | None = None,
    notes: str | None = None,
) -> int:
    day_str = str(day)
    cur = conn.execute(
        """INSERT OR REPLACE INTO daily_state
           (date, sleep_hours, stress_level, physical_state, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (day_str, sleep_hours, stress_level, physical_state, notes),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_pattern(
    conn: sqlite3.Connection,
    *,
    title: str,
    description: str | None = None,
    conditions: dict | str | None = None,
    evidence: list | str | None = None,
    counter_evidence: list | str | None = None,
    evidence_count: int = 0,
    counter_evidence_count: int = 0,
    confidence: float = 0.0,
    confidence_level: str = "low",
    status: str = "candidate",
) -> int:
    def _json(val: Any) -> str | None:
        if val is None:
            return None
        return val if isinstance(val, str) else json.dumps(val)

    cur = conn.execute(
        """INSERT INTO patterns
           (title, description, conditions, evidence, counter_evidence,
            evidence_count, counter_evidence_count, confidence, confidence_level, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, _json(conditions), _json(evidence), _json(counter_evidence),
         evidence_count, counter_evidence_count, confidence, confidence_level, status),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_self_catch_link(
    conn: sqlite3.Connection,
    *,
    self_catch_event_id: int,
    emotion_event_id: int | None = None,
    time_delta_seconds: float | None = None,
    same_trade: bool = False,
) -> int:
    cur = conn.execute(
        """INSERT INTO self_catch_links
           (self_catch_event_id, emotion_event_id, time_delta_seconds, same_trade)
           VALUES (?, ?, ?, ?)""",
        (self_catch_event_id, emotion_event_id, time_delta_seconds, int(same_trade)),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_trade_chain(
    conn: sqlite3.Connection,
    *,
    symbol: str | None = None,
    direction: str | None = None,
    outcome: str | None = None,
    pnl: float | None = None,
    status: str = "incomplete",
    opened_at: str | None = None,
    closed_at: str | None = None,
) -> int:
    """Insert a trade_chains row and return the new id."""
    cur = conn.execute(
        """INSERT INTO trade_chains
           (symbol, direction, outcome, pnl, status, opened_at, closed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (symbol, direction, outcome, pnl, status, opened_at, closed_at),
    )
    return cur.lastrowid  # type: ignore[return-value]


def update_trade_chain(
    conn: sqlite3.Connection,
    chain_id: int,
    *,
    outcome: str | None = None,
    pnl: float | None = None,
    status: str | None = None,
    closed_at: str | None = None,
    direction: str | None = None,
) -> None:
    """Update mutable fields of an existing trade chain."""
    sets: list[str] = []
    vals: list[Any] = []
    for col, val in [
        ("outcome", outcome), ("pnl", pnl), ("status", status),
        ("closed_at", closed_at), ("direction", direction),
    ]:
        if val is not None:
            sets.append(f"{col} = ?")
            vals.append(val)
    if not sets:
        return
    vals.append(chain_id)
    conn.execute(f"UPDATE trade_chains SET {', '.join(sets)} WHERE id = ?", vals)


def insert_trade_event(
    conn: sqlite3.Connection,
    *,
    chain_id: int | None = None,
    event_type: str,
    symbol: str | None = None,
    direction: str | None = None,
    price: float | None = None,
    quantity: float | None = None,
    timestamp: str = "",
    source: str = "csv",
) -> int:
    """Insert a trade_events row and return the new id."""
    cur = conn.execute(
        """INSERT INTO trade_events
           (chain_id, event_type, symbol, direction, price, quantity, timestamp, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (chain_id, event_type, symbol, direction, price, quantity, timestamp, source),
    )
    return cur.lastrowid  # type: ignore[return-value]


def insert_voice_baseline(
    conn: sqlite3.Connection,
    *,
    day: str,
    chunk_count: int = 0,
    pitch_mean: float | None = None,
    pitch_std: float | None = None,
    speech_rate_mean: float | None = None,
    speech_rate_std: float | None = None,
    energy_mean: float | None = None,
    energy_std: float | None = None,
    pause_ratio_mean: float | None = None,
    pause_ratio_std: float | None = None,
) -> int:
    """Insert or replace a voice_baseline row for a date."""
    cur = conn.execute(
        """INSERT OR REPLACE INTO voice_baseline
           (date, chunk_count, pitch_mean, pitch_std,
            speech_rate_mean, speech_rate_std,
            energy_mean, energy_std,
            pause_ratio_mean, pause_ratio_std)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (day, chunk_count, pitch_mean, pitch_std,
         speech_rate_mean, speech_rate_std,
         energy_mean, energy_std,
         pause_ratio_mean, pause_ratio_std),
    )
    return cur.lastrowid  # type: ignore[return-value]
