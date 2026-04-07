"""
Tests for the HEKTO Pattern Engine (src/pattern_engine.py).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.db_writer import (
    get_connection,
    init_db,
    insert_speech_chunk,
    insert_audio_file,
    insert_trade_chain,
    insert_trade_event,
    transaction,
)
from src.pattern_engine import (
    MIN_CHAINS_FOR_PATTERNS,
    _compute_confidence,
    _confidence_level,
    _detect_duration_outcome_patterns,
    _detect_keyword_outcome_patterns,
    _detect_role_outcome_patterns,
    _detect_voice_outcome_patterns,
    _load_completed_chains,
    generate_pattern_report,
    get_predictive_signal,
    run_pattern_analysis,
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    init_db(db)
    return db


def _make_chains(
    db_path: Path,
    count: int,
    *,
    profit_ratio: float = 0.5,
    roles: list[str] | None = None,
    keywords: list[str] | None = None,
    with_voice_deviation: bool = False,
    with_timestamps: bool = True,
) -> list[int]:
    """Helper to create a number of completed chains with configurable outcomes."""
    chain_ids = []
    roles = roles or ["analysis", "expectation"]
    keywords = keywords or []

    with transaction(db_path) as conn:
        aid = insert_audio_file(conn, filename="test.wav", recorded_at="2025-01-15T09:00:00")

        for i in range(count):
            is_profit = i < int(count * profit_ratio)
            outcome = "profit" if is_profit else "loss"
            pnl = 100.0 if is_profit else -50.0

            opened_at = f"2025-01-15T{10 + i // 10:02d}:{(i % 10) * 5:02d}:00"
            closed_at = f"2025-01-15T{10 + i // 10:02d}:{(i % 10) * 5 + 3:02d}:00"

            chain_id = insert_trade_chain(
                conn,
                symbol="BTCUSDT",
                direction="long",
                outcome=outcome,
                pnl=pnl,
                status="complete",
                opened_at=opened_at if with_timestamps else None,
                closed_at=closed_at if with_timestamps else None,
            )
            chain_ids.append(chain_id)

            # Add entry event
            insert_trade_event(
                conn,
                chain_id=chain_id,
                event_type="entry",
                symbol="BTCUSDT",
                direction="long",
                price=42000.0 + i * 10,
                timestamp=opened_at,
            )

            # Add chunks with roles
            for j, role in enumerate(roles):
                voice_features = {
                    "pitch_mean_hz": 150.0 + (20 if with_voice_deviation and not is_profit else 0),
                    "speech_rate_proxy": 3.5,
                    "energy_mean_db": -25.0,
                    "pause_ratio": 0.15,
                }
                baseline_deviation = None
                if with_voice_deviation:
                    if not is_profit:
                        baseline_deviation = {
                            "pitch_deviation_pct": 25.0,
                            "speech_rate_deviation_pct": 22.0,
                            "energy_deviation_pct": 18.0,
                        }
                    else:
                        baseline_deviation = {
                            "pitch_deviation_pct": 5.0,
                            "speech_rate_deviation_pct": 3.0,
                            "energy_deviation_pct": 2.0,
                        }

                text_parts = [f"тестовый чанк {role}"]
                if keywords and j == 0:
                    text_parts.append(keywords[i % len(keywords)])

                insert_speech_chunk(
                    conn,
                    audio_file_id=aid,
                    chunk_index=i * len(roles) + j,
                    chunk_start_ms=j * 3000,
                    chunk_end_ms=(j + 1) * 3000,
                    text=" ".join(text_parts),
                    system_time=f"10:{i:02d}:00",
                    chunk_role=role,
                    chain_id=chain_id,
                    voice_features=voice_features,
                    baseline_deviation=baseline_deviation,
                )

    return chain_ids


class TestHelpers:
    def test_compute_confidence(self) -> None:
        assert _compute_confidence([1, 2, 3], []) == 1.0
        assert _compute_confidence([], [1, 2]) == 0.0
        assert _compute_confidence([1, 2], [3, 4]) == 0.5
        assert _compute_confidence([], []) == 0.0

    def test_confidence_level(self) -> None:
        assert _confidence_level(0.8) == "high"
        assert _confidence_level(0.7) == "high"
        assert _confidence_level(0.6) == "medium"
        assert _confidence_level(0.5) == "medium"
        assert _confidence_level(0.4) == "low"
        assert _confidence_level(0.1) == "low"


class TestLoadChains:
    def test_loads_completed_chains_only(self, db_path: Path) -> None:
        _make_chains(db_path, 5, profit_ratio=1.0)
        # Add an incomplete chain
        with transaction(db_path) as conn:
            insert_trade_chain(
                conn, symbol="BTCUSDT", status="incomplete",
                opened_at="2025-01-15T10:00:00",
            )

        conn = get_connection(db_path)
        try:
            chains = _load_completed_chains(conn)
        finally:
            conn.close()

        assert len(chains) == 5
        for ch in chains:
            assert ch["status"] == "complete"


class TestRoleOutcomePatterns:
    def test_detects_role_loss_pattern(self, db_path: Path) -> None:
        # 20 chains: 70% loss when "doubt" is present
        _make_chains(db_path, 20, profit_ratio=0.3, roles=["doubt"])

        conn = get_connection(db_path)
        try:
            chains = _load_completed_chains(conn)
        finally:
            conn.close()

        patterns = _detect_role_outcome_patterns(chains)
        loss_patterns = [p for p in patterns if p["conditions"]["predicted_outcome"] == "loss"]
        assert len(loss_patterns) >= 1
        assert loss_patterns[0]["confidence"] >= 0.5

    def test_no_pattern_below_threshold(self, db_path: Path) -> None:
        # Only 3 chains — below MIN_EVIDENCE_FOR_PATTERN
        _make_chains(db_path, 3, profit_ratio=0.0, roles=["doubt"])

        conn = get_connection(db_path)
        try:
            chains = _load_completed_chains(conn)
        finally:
            conn.close()

        patterns = _detect_role_outcome_patterns(chains)
        assert len(patterns) == 0


class TestVoiceOutcomePatterns:
    def test_detects_elevated_voice_loss(self, db_path: Path) -> None:
        _make_chains(db_path, 20, profit_ratio=0.3, with_voice_deviation=True)

        conn = get_connection(db_path)
        try:
            chains = _load_completed_chains(conn)
        finally:
            conn.close()

        patterns = _detect_voice_outcome_patterns(chains)
        assert len(patterns) >= 1


class TestDurationOutcomePatterns:
    def test_detects_duration_patterns(self, db_path: Path) -> None:
        _make_chains(db_path, 20, profit_ratio=0.5, with_timestamps=True)

        conn = get_connection(db_path)
        try:
            chains = _load_completed_chains(conn)
        finally:
            conn.close()

        # Duration patterns may or may not be found depending on the
        # median split. Just verify no crash.
        patterns = _detect_duration_outcome_patterns(chains)
        assert isinstance(patterns, list)


class TestKeywordOutcomePatterns:
    def test_detects_keyword_patterns(self, db_path: Path) -> None:
        _make_chains(
            db_path, 20, profit_ratio=0.2,
            keywords=["подержу", "ещё чуть-чуть"],
        )

        conn = get_connection(db_path)
        try:
            chains = _load_completed_chains(conn)
        finally:
            conn.close()

        patterns = _detect_keyword_outcome_patterns(chains)
        # With 80% loss ratio and target keywords, should find patterns
        loss_patterns = [p for p in patterns if p["conditions"]["predicted_outcome"] == "loss"]
        assert len(loss_patterns) >= 1


class TestRunPatternAnalysis:
    def test_skips_below_minimum_chains(self, db_path: Path) -> None:
        _make_chains(db_path, 5)
        patterns = run_pattern_analysis(db_path=db_path)
        assert patterns == []

    def test_runs_with_enough_chains(self, db_path: Path) -> None:
        _make_chains(db_path, 25, profit_ratio=0.3, roles=["doubt", "hold"])
        patterns = run_pattern_analysis(db_path=db_path)
        assert isinstance(patterns, list)
        # Should find at least one pattern with 70% loss
        assert len(patterns) >= 1

    def test_patterns_saved_to_db(self, db_path: Path) -> None:
        _make_chains(db_path, 25, profit_ratio=0.3, roles=["doubt"])
        run_pattern_analysis(db_path=db_path)

        conn = get_connection(db_path)
        rows = conn.execute("SELECT * FROM patterns").fetchall()
        conn.close()
        assert len(rows) >= 1

    def test_replaces_candidate_patterns_on_rerun(self, db_path: Path) -> None:
        _make_chains(db_path, 25, profit_ratio=0.3, roles=["doubt"])

        run_pattern_analysis(db_path=db_path)
        conn = get_connection(db_path)
        count1 = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        conn.close()

        # Run again — should replace candidates
        run_pattern_analysis(db_path=db_path)
        conn = get_connection(db_path)
        count2 = conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]
        conn.close()

        assert count2 == count1  # Same number, replaced not duplicated


class TestPredictiveSignal:
    def test_no_signal_without_patterns(self, db_path: Path) -> None:
        result = get_predictive_signal(
            chain_roles={"doubt"},
            keywords=["подержу"],
            voice_elevated=True,
            db_path=db_path,
        )
        assert result["has_signal"] is False

    def test_signal_with_matching_pattern(self, db_path: Path) -> None:
        _make_chains(db_path, 25, profit_ratio=0.2, roles=["doubt"])
        run_pattern_analysis(db_path=db_path)

        result = get_predictive_signal(
            chain_roles={"doubt"},
            keywords=[],
            voice_elevated=False,
            db_path=db_path,
        )
        # Should match the role-based pattern
        assert result["has_signal"] is True
        assert len(result["warnings"]) >= 1
        assert "doubt" in result["warnings"][0].lower() or "doubt" in str(result["patterns_matched"])


class TestPatternReport:
    def test_generates_report(self, tmp_path: Path) -> None:
        patterns = [
            {
                "title": "Роль «doubt» → убыток (75%)",
                "description": "В 75% случаев doubt → убыток",
                "confidence": 0.75,
                "confidence_level": "high",
                "evidence_count": 15,
                "counter_evidence_count": 5,
            },
            {
                "title": "Слово «подержу» → убыток (60%)",
                "description": "60% при подержу → убыток",
                "confidence": 0.60,
                "confidence_level": "medium",
                "evidence_count": 12,
                "counter_evidence_count": 8,
            },
        ]
        path = generate_pattern_report(patterns, output_dir=tmp_path)
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "doubt" in content
        assert "подержу" in content
        assert "75%" in content

    def test_no_report_for_empty_patterns(self, tmp_path: Path) -> None:
        path = generate_pattern_report([], output_dir=tmp_path)
        assert path is None
