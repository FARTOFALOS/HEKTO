"""
Tests for the HEKTO immediate signal module (src/signal.py).
"""

from __future__ import annotations

import pytest

from src.signal import generate_signal, format_signal


class TestGenerateSignal:
    def test_normal_no_alert(self) -> None:
        deviation = {
            "pitch_deviation_pct": 5.0,
            "speech_rate_deviation_pct": 3.0,
            "energy_deviation_pct": -2.0,
            "pause_ratio_deviation_pct": 10.0,
        }
        sig = generate_signal(deviation)
        assert sig["alert"] is False
        assert sig["level"] == "normal"
        assert sig["messages"] == []

    def test_elevated_alert(self) -> None:
        deviation = {
            "pitch_deviation_pct": 25.0,   # above 15% threshold
            "speech_rate_deviation_pct": 5.0,
            "energy_deviation_pct": 3.0,
            "pause_ratio_deviation_pct": 10.0,
        }
        sig = generate_signal(deviation)
        assert sig["alert"] is True
        assert sig["level"] == "elevated"
        assert len(sig["messages"]) == 1

    def test_high_alert(self) -> None:
        deviation = {
            "pitch_deviation_pct": 25.0,
            "speech_rate_deviation_pct": 30.0,
            "energy_deviation_pct": 20.0,
            "pause_ratio_deviation_pct": -60.0,  # pauses disappeared
        }
        sig = generate_signal(deviation)
        assert sig["alert"] is True
        assert sig["level"] == "high"
        assert sig["alert_count"] >= 3

    def test_none_values_handled(self) -> None:
        deviation = {
            "pitch_deviation_pct": None,
            "speech_rate_deviation_pct": None,
            "energy_deviation_pct": None,
            "pause_ratio_deviation_pct": None,
        }
        sig = generate_signal(deviation)
        assert sig["alert"] is False


class TestFormatSignal:
    def test_format_normal(self) -> None:
        sig = {"alert": False, "level": "normal", "messages": []}
        text = format_signal(sig)
        assert "✅" in text

    def test_format_elevated(self) -> None:
        sig = {
            "alert": True,
            "level": "elevated",
            "messages": ["Тон голоса: выше нормы (+25%)"],
        }
        text = format_signal(sig)
        assert "⚠️" in text
        assert "Тон голоса" in text

    def test_format_high(self) -> None:
        sig = {
            "alert": True,
            "level": "high",
            "messages": ["Тон голоса: выше нормы (+25%)", "Темп речи: ускорился (+30%)", "Энергия голоса: выше нормы (+20%)"],
        }
        text = format_signal(sig)
        assert "🔴" in text
