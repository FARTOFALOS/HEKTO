"""
Tests for the one-command daily runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.run_daily as run_daily_module


class TestDiscoverRecordings:
    def test_filters_recordings_by_day(self, tmp_path: Path) -> None:
        (tmp_path / "recording_20250115_100000.wav").write_text("", encoding="utf-8")
        (tmp_path / "recording_20250115_120000.wav").write_text("", encoding="utf-8")
        (tmp_path / "recording_20250116_100000.wav").write_text("", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("", encoding="utf-8")

        recordings = run_daily_module.discover_recordings("2025-01-15", raw_dir=tmp_path)

        assert [path.name for path in recordings] == [
            "recording_20250115_100000.wav",
            "recording_20250115_120000.wav",
        ]


class TestRunDaily:
    def test_runs_pipeline_in_one_call(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        recording = raw_dir / "recording_20250115_100000.wav"
        recording.write_text("", encoding="utf-8")

        candles_csv = tmp_path / "candles.csv"
        trades_csv = tmp_path / "trades.csv"
        db_path = tmp_path / "hekto.db"
        report_path = tmp_path / "report_2025-01-15.md"

        calls: list[tuple[str, object]] = []

        monkeypatch.setattr(
            run_daily_module,
            "process_recording",
            lambda audio_path, db_path=None: calls.append(("process_recording", audio_path.name)) or 1,
        )
        monkeypatch.setattr(
            run_daily_module,
            "ingest_candles",
            lambda csv_path, symbol, db_path=None: calls.append(("ingest_candles", csv_path)) or 3,
        )
        monkeypatch.setattr(
            run_daily_module,
            "correlate_chunks_to_candles",
            lambda trading_date, symbol, db_path=None: calls.append(("correlate_chunks_to_candles", trading_date)) or 4,
        )
        monkeypatch.setattr(
            run_daily_module,
            "import_trades_csv",
            lambda csv_path, symbol=None, db_path=None: calls.append(("import_trades_csv", csv_path)) or 2,
        )
        monkeypatch.setattr(
            run_daily_module,
            "link_events_to_chains",
            lambda trading_date, db_path=None: calls.append(("link_events_to_chains", trading_date)) or 5,
        )
        monkeypatch.setattr(
            run_daily_module,
            "auto_close_stale_chains",
            lambda db_path=None: calls.append(("auto_close_stale_chains", db_path)) or 1,
        )
        monkeypatch.setattr(
            run_daily_module,
            "compute_baseline",
            lambda target_date, db_path=None: calls.append(("compute_baseline", target_date)) or {"date": target_date, "chunk_count": 5},
        )
        monkeypatch.setattr(
            run_daily_module,
            "save_baseline",
            lambda baseline, db_path=None: calls.append(("save_baseline", baseline["date"])) or 7,
        )
        monkeypatch.setattr(
            run_daily_module,
            "generate_daily_report",
            lambda day, db_path=None, output_dir=None: calls.append(("generate_daily_report", day)) or report_path,
        )

        summary = run_daily_module.run_daily(
            "2025-01-15",
            candles_csv=candles_csv,
            trades_csv=trades_csv,
            raw_dir=raw_dir,
            db_path=db_path,
        )

        assert summary == {
            "date": "2025-01-15",
            "processed_recordings": 1,
            "candles_ingested": 3,
            "chunk_links": 4,
            "trades_imported": 2,
            "event_links": 5,
            "stale_closed": 1,
            "baseline_saved": 7,
            "report_path": report_path,
        }
        assert calls == [
            ("process_recording", recording.name),
            ("ingest_candles", candles_csv),
            ("correlate_chunks_to_candles", "2025-01-15"),
            ("import_trades_csv", trades_csv),
            ("link_events_to_chains", "2025-01-15"),
            ("auto_close_stale_chains", db_path),
            ("compute_baseline", "2025-01-15"),
            ("save_baseline", "2025-01-15"),
            ("generate_daily_report", "2025-01-15"),
        ]
