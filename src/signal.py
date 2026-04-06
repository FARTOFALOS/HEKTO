"""
HEKTO immediate signal — Layer 1.

Compares current voice features against the personal baseline and
generates a simple deviation alert.

This works from day one (once baseline has ≥5 chunks) and provides
value before any patterns are discovered.

Example output:
    "Pitch +25% above baseline. Speech rate accelerated. Pauses disappeared."
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds for signaling (percentage deviation from baseline)
_ALERT_THRESHOLDS: dict[str, float] = {
    "pitch": 15.0,        # pitch deviation > 15% triggers alert
    "speech_rate": 20.0,  # speech rate deviation > 20% triggers alert
    "energy": 15.0,       # energy deviation > 15% triggers alert
    "pause_ratio": 40.0,  # pause_ratio deviation > 40% triggers alert
}


def generate_signal(deviation: dict[str, Any]) -> dict[str, Any]:
    """
    Analyze baseline deviation and produce a simple signal.

    Parameters
    ----------
    deviation : dict from baseline.compute_deviation()
        Keys like 'pitch_deviation_pct', 'speech_rate_deviation_pct', etc.

    Returns
    -------
    dict with:
        'alert': bool — True if any metric exceeds threshold
        'level': str — 'normal' | 'elevated' | 'high'
        'messages': list[str] — human-readable signal descriptions (Russian)
        'deviations': dict — the raw deviation data
    """
    messages: list[str] = []
    alert_count = 0

    checks = [
        ("pitch_deviation_pct", "pitch", "Тон голоса", "выше нормы", "ниже нормы"),
        ("speech_rate_deviation_pct", "speech_rate", "Темп речи", "ускорился", "замедлился"),
        ("energy_deviation_pct", "energy", "Энергия голоса", "выше нормы", "ниже нормы"),
        ("pause_ratio_deviation_pct", "pause_ratio", "Паузы", "исчезли", "увеличились"),
    ]

    for dev_key, threshold_key, label, msg_high, msg_low in checks:
        val = deviation.get(dev_key)
        if val is None:
            continue

        threshold = _ALERT_THRESHOLDS[threshold_key]

        if abs(val) > threshold:
            alert_count += 1
            direction = msg_high if val > 0 else msg_low
            # Special case: pause_ratio is inverted (negative = pauses disappeared)
            if threshold_key == "pause_ratio":
                direction = msg_high if val < 0 else msg_low
            messages.append(f"{label}: {direction} ({val:+.0f}%)")

    if alert_count == 0:
        level = "normal"
    elif alert_count <= 2:
        level = "elevated"
    else:
        level = "high"

    return {
        "alert": alert_count > 0,
        "level": level,
        "alert_count": alert_count,
        "messages": messages,
        "deviations": deviation,
    }


def format_signal(signal: dict[str, Any]) -> str:
    """Format a signal dict as a human-readable string (Russian)."""
    if not signal["alert"]:
        return "✅ Голос в пределах нормы."

    icon = "⚠️" if signal["level"] == "elevated" else "🔴"
    header = f"{icon} Отклонение от базовой линии:"
    body = "\n".join(f"  • {m}" for m in signal["messages"])
    return f"{header}\n{body}"
