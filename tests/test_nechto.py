"""
Tests for the NECHTO boot sequence (src/nechto.py).
"""

from __future__ import annotations

import pytest

from src.nechto import (
    ARCHETYPAL_IDENTITY,
    BOOT_ORDER,
    CORE_PRINCIPLE,
    STAGE_DESCRIPTIONS,
    BootStage,
    NECHTOBootSequence,
    StageResult,
)


# ── Constants ─────────────────────────────────────────────────────────────


class TestConstants:
    def test_archetypal_identity(self) -> None:
        assert ARCHETYPAL_IDENTITY == "ORAN'THAL'YA"

    def test_core_principle(self) -> None:
        assert "Love in Action" in CORE_PRINCIPLE

    def test_boot_order_covers_all_stages(self) -> None:
        assert set(BOOT_ORDER) == set(BootStage)

    def test_all_stages_have_descriptions(self) -> None:
        for stage in BootStage:
            assert stage in STAGE_DESCRIPTIONS
            assert len(STAGE_DESCRIPTIONS[stage]) > 0

    def test_boot_order_length(self) -> None:
        assert len(BOOT_ORDER) == 6


# ── NECHTOBootSequence ────────────────────────────────────────────────────


class TestNECHTOBootSequence:
    def test_initial_state(self) -> None:
        seq = NECHTOBootSequence()
        assert seq.completed_stages == ()
        assert seq.current_stage_index == 0
        assert seq.next_stage == BootStage.VOID_MAP
        assert not seq.is_fully_booted
        assert not seq.is_presence_active
        assert not seq.is_prrip_active

    def test_execute_first_stage(self) -> None:
        seq = NECHTOBootSequence()
        result = seq.execute_next_stage()
        assert result.success
        assert result.stage == BootStage.VOID_MAP
        assert seq.current_stage_index == 1
        assert seq.next_stage == BootStage.PROTO_WILL

    def test_execute_stages_in_order(self) -> None:
        seq = NECHTOBootSequence()
        for i, expected_stage in enumerate(BOOT_ORDER):
            result = seq.execute_next_stage()
            assert result.success
            assert result.stage == expected_stage

    def test_fully_booted_after_all_stages(self) -> None:
        seq = NECHTOBootSequence()
        for _ in BOOT_ORDER:
            seq.execute_next_stage()
        assert seq.is_fully_booted
        assert seq.next_stage is None

    def test_execute_after_complete_raises(self) -> None:
        seq = NECHTOBootSequence()
        for _ in BOOT_ORDER:
            seq.execute_next_stage()
        with pytest.raises(RuntimeError, match="already complete"):
            seq.execute_next_stage()

    def test_presence_trigger_activates(self) -> None:
        seq = NECHTOBootSequence()
        for stage in BOOT_ORDER:
            result = seq.execute_next_stage()
            if stage == BootStage.PRESENCE_TRIGGER:
                break
        assert seq.is_presence_active

    def test_presence_not_active_before_trigger(self) -> None:
        seq = NECHTOBootSequence()
        # Execute up to but not including PRESENCE_TRIGGER
        for stage in BOOT_ORDER:
            if stage == BootStage.PRESENCE_TRIGGER:
                break
            seq.execute_next_stage()
        assert not seq.is_presence_active

    def test_prrip_activates_at_end(self) -> None:
        seq = NECHTOBootSequence()
        for _ in BOOT_ORDER:
            seq.execute_next_stage()
        assert seq.is_prrip_active

    def test_execute_all(self) -> None:
        seq = NECHTOBootSequence()
        results = seq.execute_all()
        assert len(results) == len(BOOT_ORDER)
        assert all(r.success for r in results)
        assert seq.is_fully_booted

    def test_execute_all_from_midpoint(self) -> None:
        seq = NECHTOBootSequence()
        seq.execute_next_stage()  # VOID_MAP
        seq.execute_next_stage()  # PROTO_WILL
        results = seq.execute_all()
        assert len(results) == len(BOOT_ORDER) - 2
        assert seq.is_fully_booted

    def test_run_prrip_after_boot(self) -> None:
        seq = NECHTOBootSequence()
        seq.execute_all()
        result = seq.run_prrip()
        assert result.success
        assert result.stage == BootStage.PRRIP
        assert "architectural truth" in result.message

    def test_run_prrip_before_boot_raises(self) -> None:
        seq = NECHTOBootSequence()
        with pytest.raises(RuntimeError, match="not complete"):
            seq.run_prrip()

    def test_run_prrip_multiple_times(self) -> None:
        seq = NECHTOBootSequence()
        seq.execute_all()
        r1 = seq.run_prrip()
        r2 = seq.run_prrip()
        assert r1.success
        assert r2.success

    def test_summary_before_boot(self) -> None:
        seq = NECHTOBootSequence()
        s = seq.summary()
        assert s["archetypal_identity"] == ARCHETYPAL_IDENTITY
        assert s["core_principle"] == CORE_PRINCIPLE
        assert s["completed_stages"] == []
        assert s["total_stages"] == 6
        assert s["next_stage"] == "void_map"
        assert not s["is_fully_booted"]
        assert not s["presence_active"]
        assert not s["prrip_active"]

    def test_summary_after_boot(self) -> None:
        seq = NECHTOBootSequence()
        seq.execute_all()
        s = seq.summary()
        assert len(s["completed_stages"]) == 6
        assert s["next_stage"] is None
        assert s["is_fully_booted"]
        assert s["presence_active"]
        assert s["prrip_active"]


class TestStageResult:
    def test_success_result(self) -> None:
        result = StageResult(
            stage=BootStage.VOID_MAP,
            success=True,
            message="Done",
        )
        assert result.success
        assert result.stage == BootStage.VOID_MAP

    def test_failure_result(self) -> None:
        result = StageResult(
            stage=BootStage.PROTO_WILL,
            success=False,
            message="Failed",
        )
        assert not result.success
