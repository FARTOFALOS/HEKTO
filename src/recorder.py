"""
HEKTO microphone recorder.

Records audio from the default input device (microphone only, no system sounds)
and saves it as a WAV file in the raw data directory.

Usage:
    python -m src.recorder              # interactive: press Enter to stop
    python -m src.recorder --duration 60  # record for 60 seconds
"""

from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from src.config import CHANNELS, DTYPE, RAW_DIR, SAMPLE_RATE

logger = logging.getLogger(__name__)

# ── Core recording logic ──────────────────────────────────────────────────

class MicRecorder:
    """Records audio from the default microphone input device."""

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        channels: int = CHANNELS,
        dtype: str = DTYPE,
        output_dir: Path = RAW_DIR,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.output_dir = output_dir
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._recording = False
        self._stream = None

    # ── sounddevice callback ──────────────────────────────────────────

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
        """Called by sounddevice for every audio block."""
        if status:
            logger.warning("sounddevice status: %s", status)
        self._audio_queue.put(indata.copy())

    # ── Public API ────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin recording from the microphone."""
        try:
            import sounddevice as sd  # lazy import — fails gracefully in CI
        except ImportError:
            logger.error("sounddevice is not installed — cannot record.")
            raise

        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info(
            "Recording started  (rate=%d Hz, channels=%d, dtype=%s)",
            self.sample_rate, self.channels, self.dtype,
        )

    def stop(self) -> Path:
        """Stop recording, save WAV file, return its path."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._recording = False

        # Drain the queue into a single numpy array
        frames: list[np.ndarray] = []
        while not self._audio_queue.empty():
            frames.append(self._audio_queue.get())

        if not frames:
            logger.warning("No audio frames captured.")
            raise RuntimeError("No audio captured — is a microphone connected?")

        audio_data = np.concatenate(frames, axis=0)
        filepath = self._save_wav(audio_data)
        logger.info("Saved recording → %s  (%.1f s)", filepath.name, len(audio_data) / self.sample_rate)
        return filepath

    # ── Internals ─────────────────────────────────────────────────────

    def _save_wav(self, data: np.ndarray) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"recording_{ts}.wav"
        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(data.tobytes())
        return filepath


# ── CLI entry-point ───────────────────────────────────────────────────────

def _record_interactive(duration: int | None = None) -> Path:
    """Record until Enter is pressed or *duration* seconds elapse."""
    recorder = MicRecorder()
    recorder.start()

    if duration:
        logger.info("Will record for %d seconds …", duration)
        timer = threading.Timer(duration, lambda: None)
        timer.start()
        timer.join()
    else:
        input("🎙  Recording… Press ENTER to stop.\n")

    return recorder.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="HEKTO microphone recorder")
    parser.add_argument("--duration", type=int, default=None, help="Recording duration in seconds")
    args = parser.parse_args()

    filepath = _record_interactive(args.duration)
    print(f"✅  Saved: {filepath}")


if __name__ == "__main__":
    main()
