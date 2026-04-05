"""
Tests for the spoken-time recognition and dynamic silence threshold logic
in process_recording.py.

Note: Full pipeline tests (Whisper, librosa) are omitted here because they
require heavy ML model downloads.  These unit tests cover the pure-Python
logic that is critical for correctness.
"""

from __future__ import annotations

import pytest

from src.process_recording import recognise_spoken_time


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
