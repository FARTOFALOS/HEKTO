"""
HEKTO voice baseline engine.

Computes a personal rolling baseline from the last N trading days and
calculates deviations for each new speech chunk.

Spec rule:  all voice features are evaluated ONLY relative to personal baseline.
Without baseline, raw numbers are meaningless.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.config import BASELINE_DAYS, DB_PATH
from src.db_writer import get_connection, insert_voice_baseline

logger = logging.getLogger(__name__)

# Keys we track in baseline
_FEATURE_KEYS = ("pitch_mean_hz", "speech_rate_proxy", "energy_mean_db", "pause_ratio")

# Mapping from feature key → baseline table columns (mean, std)
_FEATURE_TO_COLS: dict[str, tuple[str, str]] = {
    "pitch_mean_hz": ("pitch_mean", "pitch_std"),
    "speech_rate_proxy": ("speech_rate_mean", "speech_rate_std"),
    "energy_mean_db": ("energy_mean", "energy_std"),
    "pause_ratio": ("pause_ratio_mean", "pause_ratio_std"),
}


def compute_baseline(
    target_date: str | date | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """
    Compute voice baseline from the last BASELINE_DAYS trading days
    ending *before* target_date.

    Returns a dict with mean/std for each tracked feature, or None if
    insufficient data (< 5 chunks total).
    """
    if target_date is None:
        target_date = date.today()
    day_str = str(target_date)

    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        # Collect voice_features from the last BASELINE_DAYS worth of
        # audio files recorded BEFORE target_date.
        rows = conn.execute(
            """SELECT sc.voice_features
               FROM speech_chunks sc
               JOIN audio_files af ON sc.audio_file_id = af.id
               WHERE af.recorded_at < ?
               ORDER BY af.recorded_at DESC""",
            (f"{day_str}T00:00:00",),
        ).fetchall()
    finally:
        conn.close()

    # Parse voice_features JSON
    feature_lists: dict[str, list[float]] = {k: [] for k in _FEATURE_KEYS}
    seen_dates: set[str] = set()
    for row in rows:
        vf = row["voice_features"]
        if not vf:
            continue
        if isinstance(vf, str):
            vf = json.loads(vf)
        for key in _FEATURE_KEYS:
            val = vf.get(key)
            if val is not None:
                feature_lists[key].append(float(val))

    total_chunks = max(len(v) for v in feature_lists.values()) if feature_lists else 0
    if total_chunks < 5:
        logger.info("Baseline: insufficient data (%d chunks, need ≥5)", total_chunks)
        return None

    result: dict[str, Any] = {"chunk_count": total_chunks, "date": day_str}
    for key in _FEATURE_KEYS:
        vals = feature_lists[key]
        if len(vals) >= 2:
            result[f"{key}_mean"] = statistics.mean(vals)
            result[f"{key}_std"] = statistics.stdev(vals)
        elif len(vals) == 1:
            result[f"{key}_mean"] = vals[0]
            result[f"{key}_std"] = 0.0
        else:
            result[f"{key}_mean"] = None
            result[f"{key}_std"] = None

    logger.info("Baseline computed for %s from %d chunks", day_str, total_chunks)
    return result


def save_baseline(
    baseline: dict[str, Any],
    db_path: Path | str | None = None,
) -> int:
    """Persist a computed baseline to the voice_baseline table."""
    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        row_id = insert_voice_baseline(
            conn,
            day=baseline["date"],
            chunk_count=baseline.get("chunk_count", 0),
            pitch_mean=baseline.get("pitch_mean_hz_mean"),
            pitch_std=baseline.get("pitch_mean_hz_std"),
            speech_rate_mean=baseline.get("speech_rate_proxy_mean"),
            speech_rate_std=baseline.get("speech_rate_proxy_std"),
            energy_mean=baseline.get("energy_mean_db_mean"),
            energy_std=baseline.get("energy_mean_db_std"),
            pause_ratio_mean=baseline.get("pause_ratio_mean"),
            pause_ratio_std=baseline.get("pause_ratio_std"),
        )
        conn.commit()
        return row_id
    finally:
        conn.close()


def get_latest_baseline(
    target_date: str | date | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    """
    Fetch the most recent baseline on or before target_date.

    Returns a dict with baseline values, or None if none exists.
    """
    if target_date is None:
        target_date = date.today()
    day_str = str(target_date)

    db = db_path or DB_PATH
    conn = get_connection(db)
    try:
        row = conn.execute(
            """SELECT * FROM voice_baseline
               WHERE date <= ?
               ORDER BY date DESC LIMIT 1""",
            (day_str,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None
    return dict(row)


def compute_deviation(
    voice_features: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """
    Compute percentage deviation of current voice_features from baseline.

    Returns a dict like:
        {
            "pitch_deviation_pct": +25.3,
            "speech_rate_deviation_pct": -10.1,
            "energy_deviation_pct": +5.0,
            "pause_ratio_deviation_pct": -50.0,
        }

    Positive = above baseline, negative = below.
    If baseline std > 0, also includes z-score.
    """
    result: dict[str, Any] = {}

    mapping = {
        "pitch_mean_hz": ("pitch_mean", "pitch_std", "pitch"),
        "speech_rate_proxy": ("speech_rate_mean", "speech_rate_std", "speech_rate"),
        "energy_mean_db": ("energy_mean", "energy_std", "energy"),
        "pause_ratio": ("pause_ratio_mean", "pause_ratio_std", "pause_ratio"),
    }

    for feat_key, (bl_mean_col, bl_std_col, out_prefix) in mapping.items():
        current = voice_features.get(feat_key)
        bl_mean = baseline.get(bl_mean_col)
        bl_std = baseline.get(bl_std_col)

        if current is None or bl_mean is None or bl_mean == 0:
            result[f"{out_prefix}_deviation_pct"] = None
            result[f"{out_prefix}_z_score"] = None
            continue

        deviation_pct = round(((current - bl_mean) / abs(bl_mean)) * 100, 1)
        result[f"{out_prefix}_deviation_pct"] = deviation_pct

        if bl_std and bl_std > 0:
            result[f"{out_prefix}_z_score"] = round((current - bl_mean) / bl_std, 2)
        else:
            result[f"{out_prefix}_z_score"] = None

    return result
