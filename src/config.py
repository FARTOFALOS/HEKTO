"""
HEKTO configuration module.

Centralises all paths, constants and tuneable parameters so that every other
module imports from here instead of hard-coding values.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── Root paths ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
PATTERNS_DIR = DATA_DIR / "patterns"
DB_PATH = PROCESSED_DIR / "hekto.db"

# Ensure directories exist at import time
for _d in (RAW_DIR, PROCESSED_DIR, PATTERNS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Recording defaults ────────────────────────────────────────────────────
SAMPLE_RATE: int = 16_000          # Hz — Whisper expects 16 kHz
CHANNELS: int = 1                  # mono
DTYPE: str = "int16"

# ── Silence / segmentation ────────────────────────────────────────────────
# Dynamic threshold: silence_threshold = mean_dB - SILENCE_OFFSET_DB
SILENCE_OFFSET_DB: float = 14.0
MIN_SILENCE_LEN_MS: int = 700      # ms of silence to split on
MIN_CHUNK_LEN_MS: int = 1_000      # discard chunks shorter than this
KEEP_SILENCE_MS: int = 300          # keep at chunk edges

# ── Voice feature analysis ────────────────────────────────────────────────
PAUSE_THRESHOLD_DB: float = -40.0   # frames below this are counted as pauses

# ── Market correlation ────────────────────────────────────────────────────
MAX_CANDLE_CORRELATION_MINUTES: int = 5  # max offset to match a chunk to a candle

# ── Whisper ───────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("HEKTO_WHISPER_MODEL", "base")
WHISPER_LANGUAGE: str = os.getenv("HEKTO_WHISPER_LANG", "ru")

# ── Voice features ────────────────────────────────────────────────────────
# Baseline window: how many past chunks to use for personal baseline
BASELINE_WINDOW: int = 50

# ── Spoken-time recognition ───────────────────────────────────────────────
# Regex patterns to catch times the trader says aloud (e.g. "десять четырнадцать")
# Handled in process_recording.py

# ── Market data ───────────────────────────────────────────────────────────
DEFAULT_SYMBOL: str = os.getenv("HEKTO_SYMBOL", "BTCUSDT")
DEFAULT_TIMEFRAME: str = "1m"

# ── Logging ───────────────────────────────────────────────────────────────
import logging

LOG_LEVEL: str = os.getenv("HEKTO_LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s  %(name)-22s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
