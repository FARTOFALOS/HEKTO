"""
HEKTO recording processor.

Takes a raw WAV file and:
 1. Computes a dynamic silence threshold  (mean_dB − 14).
 2. Splits audio on silence into speech chunks.
 3. Runs Whisper for transcription + timestamps.
 4. Extracts basic voice features via librosa.
 5. Recognises spoken time references.
 6. Persists everything into SQLite.
"""

from __future__ import annotations

import json
import logging
import math
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from src.config import (
    DB_PATH,
    KEEP_SILENCE_MS,
    MIN_CHUNK_LEN_MS,
    MIN_SILENCE_LEN_MS,
    PROCESSED_DIR,
    SAMPLE_RATE,
    SILENCE_OFFSET_DB,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
)
from src.db_writer import (
    init_db,
    insert_audio_file,
    insert_speech_chunk,
    transaction,
)

logger = logging.getLogger(__name__)

# ── Spoken-time recognition ───────────────────────────────────────────────

# Maps Russian number words to digits (covers 0–59 and common hour words)
_RU_NUMBERS: dict[str, int] = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "десять": 10, "одиннадцать": 11, "двенадцать": 12,
    "тринадцать": 13, "четырнадцать": 14, "пятнадцать": 15,
    "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
    "девятнадцать": 19, "двадцать": 20, "тридцать": 30,
    "сорок": 40, "пятьдесят": 50,
}

# Compound numbers (e.g. "двадцать один") are handled via two-pass lookup
# in recognise_spoken_time by combining tens + ones.

# Regex: digital times like "10:14", "10 14", "10-14"
_DIGIT_TIME_RE = re.compile(r"\b(\d{1,2})[:\s\-](\d{2})\b")


def _words_to_number(word: str) -> int | None:
    """Convert a single Russian number word to int, or None."""
    return _RU_NUMBERS.get(word.lower().strip())


def recognise_spoken_time(text: str) -> tuple[str | None, float]:
    """
    Try to extract a clock time from *text*.

    Returns (time_str, confidence) where time_str is "HH:MM" or None.
    confidence is 0.0–1.0.
    """
    # 1) Try digit pattern first  (e.g. "10:14")
    m = _DIGIT_TIME_RE.search(text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}", 0.95

    # 2) Try Russian word patterns
    words = text.lower().split()

    def _try_number_at(idx: int) -> tuple[int | None, int]:
        """Try to parse a number starting at words[idx]. Returns (value, words_consumed)."""
        if idx >= len(words):
            return None, 0
        w1 = _words_to_number(words[idx])
        if w1 is None:
            return None, 0
        # Check for compound: "двадцать один" = 20 + 1
        if idx + 1 < len(words) and w1 in (20, 30, 40, 50):
            w2 = _words_to_number(words[idx + 1])
            if w2 is not None and 1 <= w2 <= 9:
                return w1 + w2, 2
        return w1, 1

    for i in range(len(words)):
        h_val, h_consumed = _try_number_at(i)
        if h_val is None or not (0 <= h_val <= 23):
            continue
        m_val, m_consumed = _try_number_at(i + h_consumed)
        if m_val is not None and 0 <= m_val <= 59:
            return f"{h_val:02d}:{m_val:02d}", 0.80

    return None, 0.0

# ── Dynamic silence threshold ─────────────────────────────────────────────

def compute_dynamic_threshold(audio_segment: "pydub.AudioSegment") -> tuple[float, float]:
    """
    Compute a per-file dynamic silence threshold.

    Returns (silence_threshold_dBFS, mean_dBFS).
    """
    mean_db = audio_segment.dBFS
    threshold = mean_db - SILENCE_OFFSET_DB
    logger.info("Dynamic silence threshold: mean=%.1f dBFS, threshold=%.1f dBFS", mean_db, threshold)
    return threshold, mean_db

# ── Audio segmentation ────────────────────────────────────────────────────

def segment_audio(audio_path: Path) -> tuple[list[tuple[int, int, "pydub.AudioSegment"]], float, float]:
    """
    Split *audio_path* on silence using pydub with a dynamic threshold.

    Returns:
        segments: list of (start_ms, end_ms, AudioSegment)
        silence_threshold_db: the threshold used
        mean_db: mean loudness of the whole file
    """
    from pydub import AudioSegment
    from pydub.silence import detect_nonsilent

    audio = AudioSegment.from_file(str(audio_path))

    threshold, mean_db = compute_dynamic_threshold(audio)

    nonsilent_ranges = detect_nonsilent(
        audio,
        min_silence_len=MIN_SILENCE_LEN_MS,
        silence_thresh=threshold,
        seek_step=10,
    )

    segments: list[tuple[int, int, AudioSegment]] = []
    for start_ms, end_ms in nonsilent_ranges:
        # Add a small buffer of silence at edges
        seg_start = max(0, start_ms - KEEP_SILENCE_MS)
        seg_end = min(len(audio), end_ms + KEEP_SILENCE_MS)
        duration = seg_end - seg_start
        if duration < MIN_CHUNK_LEN_MS:
            logger.debug("Skipping short segment (%d ms)", duration)
            continue
        segments.append((seg_start, seg_end, audio[seg_start:seg_end]))

    logger.info("Segmented %s into %d chunks", audio_path.name, len(segments))
    return segments, threshold, mean_db

# ── Voice features ────────────────────────────────────────────────────────

def extract_voice_features(audio_segment: "pydub.AudioSegment", sr: int = SAMPLE_RATE) -> dict[str, Any]:
    """
    Extract basic prosodic / voice features from an audio segment.

    Returns a dict with:
        speech_rate_proxy  – number of energy onsets (rough word count proxy)
        pitch_mean_hz      – mean fundamental frequency
        pitch_std_hz       – pitch variability
        energy_mean_db     – mean RMS energy in dB
        energy_std_db      – energy variability
        pause_ratio        – fraction of near-silent frames
        duration_sec       – segment length
    """
    import librosa

    # Convert pydub segment → numpy float32
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
    if audio_segment.channels > 1:
        samples = samples.reshape((-1, audio_segment.channels)).mean(axis=1)
    samples = samples / (2**15)  # int16 → float
    # Resample if needed
    if audio_segment.frame_rate != sr:
        samples = librosa.resample(samples, orig_sr=audio_segment.frame_rate, target_sr=sr)

    duration = len(samples) / sr

    # Pitch via pyin
    f0, voiced_flag, _ = librosa.pyin(samples, fmin=60, fmax=500, sr=sr)
    f0_voiced = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
    pitch_mean = float(np.nanmean(f0_voiced)) if len(f0_voiced) > 0 else 0.0
    pitch_std = float(np.nanstd(f0_voiced)) if len(f0_voiced) > 0 else 0.0

    # Energy (RMS)
    rms = librosa.feature.rms(y=samples, frame_length=2048, hop_length=512)[0]
    rms_db = librosa.amplitude_to_db(rms, ref=np.max)
    energy_mean = float(np.mean(rms_db))
    energy_std = float(np.std(rms_db))

    # Pause ratio (frames below threshold)
    from src.config import PAUSE_THRESHOLD_DB
    pause_ratio = float(np.mean(rms_db < PAUSE_THRESHOLD_DB))

    # Speech rate proxy via onset detection
    onsets = librosa.onset.onset_detect(y=samples, sr=sr, units="time")
    speech_rate_proxy = len(onsets) / duration if duration > 0 else 0.0

    return {
        "speech_rate_proxy": round(speech_rate_proxy, 2),
        "pitch_mean_hz": round(pitch_mean, 2),
        "pitch_std_hz": round(pitch_std, 2),
        "energy_mean_db": round(energy_mean, 2),
        "energy_std_db": round(energy_std, 2),
        "pause_ratio": round(pause_ratio, 3),
        "duration_sec": round(duration, 2),
    }

# ── Whisper transcription ─────────────────────────────────────────────────

def transcribe_chunk(audio_segment: "pydub.AudioSegment") -> str:
    """Transcribe an audio segment using Whisper. Returns text."""
    import whisper

    model = whisper.load_model(WHISPER_MODEL)

    # Write segment to a temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_segment.export(tmp.name, format="wav")
        tmp_path = tmp.name

    result = model.transcribe(tmp_path, language=WHISPER_LANGUAGE)
    Path(tmp_path).unlink(missing_ok=True)
    return result.get("text", "").strip()

# ── Main processing pipeline ──────────────────────────────────────────────

def process_recording(
    audio_path: Path,
    recording_start: datetime | None = None,
    db_path: Path | str | None = None,
) -> int:
    """
    Full pipeline: segment → transcribe → features → DB.

    Parameters
    ----------
    audio_path : path to raw WAV
    recording_start : wall-clock time when recording began (for system_time calc)
    db_path : override database path (for testing)

    Returns
    -------
    audio_file_id inserted into the database.
    """
    from pydub import AudioSegment as _AS  # ensure pydub is available

    db = db_path or DB_PATH
    init_db(db)

    if recording_start is None:
        # Try to infer from filename  recording_YYYYMMDD_HHMMSS.wav
        stem = audio_path.stem
        try:
            recording_start = datetime.strptime(stem, "recording_%Y%m%d_%H%M%S")
        except ValueError:
            recording_start = datetime.now()

    # 1 — Segment
    segments, silence_thresh, mean_db = segment_audio(audio_path)

    full_audio = _AS.from_file(str(audio_path))
    duration_sec = len(full_audio) / 1000.0

    # 2 — Persist audio_file row first
    with transaction(db) as conn:
        audio_file_id = insert_audio_file(
            conn,
            filename=audio_path.name,
            recorded_at=recording_start.isoformat(),
            duration_sec=duration_sec,
            sample_rate=SAMPLE_RATE,
            silence_threshold_db=silence_thresh,
            mean_db=mean_db,
        )

    # 3 — Process each chunk
    for idx, (start_ms, end_ms, seg) in enumerate(segments):
        logger.info("Processing chunk %d/%d  (%d–%d ms)", idx + 1, len(segments), start_ms, end_ms)

        text = transcribe_chunk(seg)
        features = extract_voice_features(seg)
        spoken_time, time_conf = recognise_spoken_time(text)

        # system_time = recording start + chunk midpoint offset
        midpoint_offset = timedelta(milliseconds=(start_ms + end_ms) / 2)
        system_time = (recording_start + midpoint_offset).strftime("%H:%M:%S")

        with transaction(db) as conn:
            insert_speech_chunk(
                conn,
                audio_file_id=audio_file_id,
                chunk_index=idx,
                chunk_start_ms=start_ms,
                chunk_end_ms=end_ms,
                text=text,
                spoken_time=spoken_time,
                system_time=system_time,
                time_confidence=time_conf,
                voice_features=features,
            )

    logger.info("Finished processing %s  (%d chunks)", audio_path.name, len(segments))
    return audio_file_id


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Process a HEKTO recording")
    parser.add_argument("audio", type=Path, help="Path to raw WAV file")
    parser.add_argument("--db", type=Path, default=None, help="Override DB path")
    args = parser.parse_args()

    process_recording(args.audio, db_path=args.db)


if __name__ == "__main__":
    main()
