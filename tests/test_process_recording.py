"""
Tests for the spoken-time recognition and dynamic silence threshold logic
in process_recording.py.

Note: Full pipeline tests (Whisper, librosa) are omitted here because they
require heavy ML model downloads.  These unit tests cover the pure-Python
logic that is critical for correctness.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.process_recording as process_recording_module
from src.process_recording import process_recording, recognise_spoken_time


class TestRecogniseSpokenTime:
    """Unit tests for spoken-time extraction from text."""

    def test_digit_colon(self) -> None:
        time_str, conf = recognise_spoken_time("сейчас 10:14 примерно")
        assert time_str == "10:14"
        assert conf >= 0.9

    def test_digit_space(self) -> None:
        time_str, conf = recognise_spoken_time("время 9 05")
        assert time_str == "09:05"
        assert conf >= 0.9

    def test_digit_dash(self) -> None:
        time_str, conf = recognise_spoken_time("вход в 14-30")
        assert time_str == "14:30"
        assert conf >= 0.9

    def test_russian_words(self) -> None:
        time_str, conf = recognise_spoken_time("десять четырнадцать")
        assert time_str == "10:14"
        assert conf >= 0.7

    def test_russian_words_in_sentence(self) -> None:
        time_str, conf = recognise_spoken_time("ну вот сейчас пять тридцать рынок открылся")
        assert time_str == "05:30"
        assert conf >= 0.7

    def test_no_time(self) -> None:
        time_str, conf = recognise_spoken_time("просто мысли вслух")
        assert time_str is None
        assert conf == 0.0

    def test_invalid_hour(self) -> None:
        time_str, _ = recognise_spoken_time("25:00")
        assert time_str is None

    def test_invalid_minute(self) -> None:
        time_str, _ = recognise_spoken_time("10:61")
        assert time_str is None

    def test_single_digit_hour(self) -> None:
        time_str, conf = recognise_spoken_time("3:05 утра")
        assert time_str == "03:05"
        assert conf >= 0.9

    def test_compound_russian_minutes(self) -> None:
        """Compound: двадцать один = 21."""
        time_str, conf = recognise_spoken_time("десять двадцать один")
        assert time_str == "10:21"
        assert conf >= 0.7

    def test_compound_russian_hour_and_minute(self) -> None:
        """Compound: двадцать один тридцать пять = 21:35."""
        time_str, conf = recognise_spoken_time("двадцать один тридцать пять")
        assert time_str == "21:35"
        assert conf >= 0.7


class TestProcessRecording:
    def test_process_recording_loads_whisper_once(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        class _FakeLoadedAudio:
            def __len__(self) -> int:
                return 6000

        fake_pydub = SimpleNamespace(
            AudioSegment=SimpleNamespace(from_file=staticmethod(lambda _: _FakeLoadedAudio()))
        )
        monkeypatch.setitem(sys.modules, "pydub", fake_pydub)

        model = object()
        load_calls = {"count": 0}
        transcribe_models: list[object] = []

        monkeypatch.setattr(
            process_recording_module,
            "segment_audio",
            lambda _: (
                [(0, 1000, object()), (2000, 3000, object())],
                -45.0,
                -31.0,
            ),
        )
        monkeypatch.setattr(
            process_recording_module,
            "load_whisper_model",
            lambda: load_calls.__setitem__("count", load_calls["count"] + 1) or model,
        )
        monkeypatch.setattr(
            process_recording_module,
            "transcribe_chunk",
            lambda _segment, model=None: transcribe_models.append(model) or "тест",
        )
        monkeypatch.setattr(
            process_recording_module,
            "extract_voice_features",
            lambda _segment: {
                "pitch_mean_hz": 120.0,
                "speech_rate_proxy": 3.0,
                "energy_mean_db": -20.0,
                "pause_ratio": 0.1,
            },
        )
        monkeypatch.setattr(process_recording_module, "recognise_spoken_time", lambda _text: (None, 0.0))
        monkeypatch.setattr(process_recording_module, "classify_chunk_role", lambda _text: "other")
        monkeypatch.setattr(process_recording_module, "get_latest_baseline", lambda **_kwargs: None)
        monkeypatch.setattr(process_recording_module, "detect_chain_open", lambda _text: False)
        monkeypatch.setattr(process_recording_module, "detect_chain_close", lambda _text: False)

        audio_path = tmp_path / "recording_20250115_100000.wav"
        audio_file_id = process_recording(
            audio_path,
            recording_start=datetime(2025, 1, 15, 10, 0, 0),
            db_path=tmp_path / "test.db",
        )

        assert audio_file_id > 0
        assert load_calls["count"] == 1
        assert transcribe_models == [model, model]
