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
    voice_features  TEXT,                       -- JSON blob
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
    evidence_count  INTEGER DEFAULT 0,
    confidence      REAL    DEFAULT 0.0,
    status          TEXT    DEFAULT 'candidate', -- candidate | confirmed | rejected
    last_updated    TEXT    NOT NULL DEFAULT (datetime('now')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chunks_audio ON speech_chunks(audio_file_id);
CREATE INDEX IF NOT EXISTS idx_chunks_self_catch ON speech_chunks(self_catch_flag);
CREATE INDEX IF NOT EXISTS idx_market_ts ON market_context(timestamp, symbol);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_state(date);
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
    emotion: str | None = None,
    self_catch_flag: bool = False,
    trade_context_id: int | None = None,
) -> int:
    """Insert a speech_chunks row and return the new id."""
    cur = conn.execute(
        """INSERT INTO speech_chunks
           (audio_file_id, chunk_index, chunk_start_ms, chunk_end_ms,
            text, spoken_time, system_time, time_confidence,
            voice_features, emotion, self_catch_flag, trade_context_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            audio_file_id, chunk_index, chunk_start_ms, chunk_end_ms,
            text, spoken_time, system_time, time_confidence,
            voice_features if isinstance(voice_features, str) else (json.dumps(voice_features) if voice_features else None),
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
) -> int:
    cur = conn.execute(
        """INSERT INTO market_context
           (timestamp, symbol, timeframe, open, high, low, close, volume, volatility)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, symbol, timeframe, open_, high, low, close, volume, volatility),
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
    evidence_count: int = 0,
    confidence: float = 0.0,
    status: str = "candidate",
) -> int:
    cur = conn.execute(
        """INSERT INTO patterns
           (title, description, evidence_count, confidence, status)
           VALUES (?, ?, ?, ?, ?)""",
        (title, description, evidence_count, confidence, status),
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
