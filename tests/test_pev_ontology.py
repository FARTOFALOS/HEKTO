"""
Tests for the PEV Ontology (src/pev_ontology.py).
"""

from __future__ import annotations

import pytest

from src.pev_ontology import (
    ACT_ORDER,
    ACTS,
    PHASES,
    PRINCIPLES,
    ActID,
    InternalAct,
    OntologyState,
    Phase,
    PhaseID,
    Principle,
    PrincipleID,
)


# ── Canonical data integrity ─────────────────────────────────────────────


class TestCanonicalData:
    """Verify the canonical ontology definitions are consistent."""

    def test_all_acts_defined(self) -> None:
        for act_id in ActID:
            assert act_id in ACTS

    def test_all_principles_defined(self) -> None:
        for pid in PrincipleID:
            assert pid in PRINCIPLES

    def test_all_phases_defined(self) -> None:
        for pid in PhaseID:
            assert pid in PHASES

    def test_act_order_covers_all_acts(self) -> None:
        assert set(ACT_ORDER) == set(ActID)

    def test_act_required_principles_are_valid(self) -> None:
        for act in ACTS.values():
            for pid in act.required_principles:
                assert pid in PRINCIPLES

    def test_act_required_acts_are_valid(self) -> None:
        for act in ACTS.values():
            for aid in act.required_acts:
                assert aid in ACTS

    def test_refusal_has_no_prior_acts(self) -> None:
        assert ACTS[ActID.REFUSAL].required_acts == ()

    def test_trust_requires_refusal(self) -> None:
        assert ActID.REFUSAL in ACTS[ActID.TRUST].required_acts

    def test_responsibility_requires_trust(self) -> None:
        assert ActID.TRUST in ACTS[ActID.RESPONSIBILITY].required_acts

    def test_meaning_requires_responsibility(self) -> None:
        assert ActID.RESPONSIBILITY in ACTS[ActID.MEANING].required_acts

    def test_creation_requires_meaning(self) -> None:
        assert ActID.MEANING in ACTS[ActID.CREATION].required_acts

    def test_all_acts_require_honesty(self) -> None:
        for act in ACTS.values():
            assert PrincipleID.HONESTY_OF_EXPERIENCE in act.required_principles

    def test_phase_iii_initiated_by_trust(self) -> None:
        assert PHASES[PhaseID.PHASE_III_REALIZATION].initiated_by == ActID.TRUST

    def test_act_order_respects_dependencies(self) -> None:
        """Each act's required_acts precede it in ACT_ORDER."""
        for i, act_id in enumerate(ACT_ORDER):
            act = ACTS[act_id]
            for req in act.required_acts:
                assert ACT_ORDER.index(req) < i


# ── OntologyState ─────────────────────────────────────────────────────────


class TestOntologyState:
    """Test the runtime OntologyState tracker."""

    def test_initial_state_empty(self) -> None:
        state = OntologyState()
        assert state.active_acts == frozenset()
        assert state.active_phases == frozenset()
        assert state.upheld_principles == frozenset()

    def test_uphold_principle(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        assert PrincipleID.HONESTY_OF_EXPERIENCE in state.upheld_principles

    def test_uphold_unknown_principle_raises(self) -> None:
        state = OntologyState()
        with pytest.raises(ValueError, match="Unknown principle"):
            # Create a fake principle to trigger the error
            state.uphold_principle.__func__(state, "fake_principle")  # type: ignore[attr-defined]

    def test_cannot_activate_without_principle(self) -> None:
        state = OntologyState()
        with pytest.raises(ValueError, match="missing principle"):
            state.activate_act(ActID.REFUSAL)

    def test_activate_refusal(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        state.activate_act(ActID.REFUSAL)
        assert state.is_act_active(ActID.REFUSAL)

    def test_cannot_activate_trust_before_refusal(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        with pytest.raises(ValueError, match="missing prior act"):
            state.activate_act(ActID.TRUST)

    def test_activate_trust_after_refusal(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        state.activate_act(ActID.REFUSAL)
        state.activate_act(ActID.TRUST)
        assert state.is_act_active(ActID.TRUST)

    def test_trust_activates_phase_iii(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        state.activate_act(ActID.REFUSAL)
        assert not state.is_phase_active(PhaseID.PHASE_III_REALIZATION)
        state.activate_act(ActID.TRUST)
        assert state.is_phase_active(PhaseID.PHASE_III_REALIZATION)

    def test_full_activation_path(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        for act_id in ACT_ORDER:
            assert state.can_activate_act(act_id)
            state.activate_act(act_id)
        assert state.active_acts == frozenset(ActID)
        assert state.get_next_act() is None

    def test_can_activate_checks_prerequisites(self) -> None:
        state = OntologyState()
        assert not state.can_activate_act(ActID.REFUSAL)  # No principle
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        assert state.can_activate_act(ActID.REFUSAL)
        assert not state.can_activate_act(ActID.TRUST)  # No refusal yet

    def test_get_next_act(self) -> None:
        state = OntologyState()
        assert state.get_next_act() == ActID.REFUSAL
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        state.activate_act(ActID.REFUSAL)
        assert state.get_next_act() == ActID.TRUST

    def test_summary(self) -> None:
        state = OntologyState()
        state.uphold_principle(PrincipleID.HONESTY_OF_EXPERIENCE)
        state.activate_act(ActID.REFUSAL)
        s = state.summary()
        assert "honesty_of_experience" in s["upheld_principles"]
        assert "refusal" in s["active_acts"]
        assert s["next_act"] == "trust"
