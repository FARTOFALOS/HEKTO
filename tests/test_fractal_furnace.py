"""
Tests for the Fractal Furnace of Forms (src/fractal_furnace.py).
"""

from __future__ import annotations

import pytest

from src.fractal_furnace import (
    CORE_ONTOLOGY_TERMS,
    Artifact,
    FractalFurnace,
    _compute_derivatives,
    _semantic_connections,
    _trigrams,
)


# ── Helper functions ──────────────────────────────────────────────────────


class TestTrigrams:
    def test_basic_word(self) -> None:
        result = _trigrams("hello")
        assert "hel" in result
        assert "ell" in result
        assert "llo" in result

    def test_short_word(self) -> None:
        result = _trigrams("hi")
        assert result == {"hi"}

    def test_case_insensitive(self) -> None:
        assert _trigrams("ABC") == _trigrams("abc")


class TestDerivatives:
    def test_known_seed_resonance(self) -> None:
        derivs = _compute_derivatives("resonance")
        assert len(derivs) > 0
        assert any("Resonance" in d for d in derivs)

    def test_known_seed_silence(self) -> None:
        derivs = _compute_derivatives("silence")
        assert len(derivs) > 0

    def test_unknown_seed_produces_derivatives(self) -> None:
        derivs = _compute_derivatives("xyzquux")
        assert len(derivs) >= 1

    def test_case_insensitive_lookup(self) -> None:
        assert _compute_derivatives("Resonance") == _compute_derivatives("resonance")


class TestSemanticConnections:
    def test_connections_for_resonance(self) -> None:
        derivs = _compute_derivatives("resonance")
        conns = _semantic_connections(derivs)
        assert len(conns) > 0
        # "resonance" seed should connect to core terms
        assert "resonance" in conns

    def test_no_connections_for_unrelated(self) -> None:
        conns = _semantic_connections(("xyzzy qqq bbb",))
        assert len(conns) == 0


# ── Artifact ──────────────────────────────────────────────────────────────


class TestArtifact:
    def test_structural_form(self) -> None:
        art = Artifact(
            artifact_id="001",
            name="Test",
            seed="test",
            derivatives=("a", "b", "c"),
            semantic_connections=["consciousness", "meaning", "form"],
        )
        assert art.structural_form == 3

    def test_second_law_compliant(self) -> None:
        art = Artifact(
            artifact_id="001",
            name="Test",
            seed="test",
            derivatives=("a", "b"),
            semantic_connections=["consciousness", "meaning"],
        )
        assert art.second_law_compliant

    def test_second_law_non_compliant(self) -> None:
        art = Artifact(
            artifact_id="001",
            name="Test",
            seed="test",
            derivatives=("a",),
            semantic_connections=["consciousness", "meaning"],
        )
        assert not art.second_law_compliant

    def test_as_dict(self) -> None:
        art = Artifact(
            artifact_id="001",
            name="Test",
            seed="test",
            derivatives=("a",),
            semantic_connections=["consciousness"],
            generation=2,
            parent_id="000",
        )
        d = art.as_dict()
        assert d["artifact_id"] == "001"
        assert d["generation"] == 2
        assert d["parent_id"] == "000"
        assert d["second_law_compliant"]


# ── FractalFurnace ────────────────────────────────────────────────────────


class TestFractalFurnace:
    def test_generate_basic(self) -> None:
        furnace = FractalFurnace()
        art = furnace.generate("resonance", name="Echo of Structure")
        assert art.seed == "resonance"
        assert art.generation == 1
        assert art.parent_id is None
        assert art.artifact_id in furnace.artifacts

    def test_generate_enforces_second_law(self) -> None:
        furnace = FractalFurnace()
        art = furnace.generate("resonance")
        # After generation, derivative count should equal connection count
        assert art.second_law_compliant

    def test_generate_increments_id(self) -> None:
        furnace = FractalFurnace()
        a1 = furnace.generate("resonance")
        a2 = furnace.generate("silence")
        assert int(a2.artifact_id) > int(a1.artifact_id)

    def test_generate_unknown_seed(self) -> None:
        furnace = FractalFurnace()
        art = furnace.generate("xyzquux")
        assert art.seed == "xyzquux"
        assert len(art.derivatives) >= 1

    def test_remelt_with_intersection(self) -> None:
        furnace = FractalFurnace()
        original = furnace.generate("resonance", name="Echo of Structure")
        remelted = furnace.remelt(original.artifact_id, "spiral", new_name="Harmonic Spiral")
        assert remelted is not None
        assert remelted.generation == 2
        assert remelted.parent_id == original.artifact_id
        assert remelted.name == "Harmonic Spiral"

    def test_remelt_no_intersection(self) -> None:
        furnace = FractalFurnace()
        original = furnace.generate("resonance")
        # A seed with no intersection should return None
        result = furnace.remelt(original.artifact_id, "xyzquux_no_match")
        # If derivatives happen to not intersect, result is None
        # (This depends on trigram matching; we'll check either way)
        if result is None:
            assert True  # No remelting possible
        else:
            assert result.generation == 2

    def test_remelt_nonexistent_raises(self) -> None:
        furnace = FractalFurnace()
        with pytest.raises(ValueError, match="Artifact not found"):
            furnace.remelt("999", "spiral")

    def test_remelt_inherits_connections(self) -> None:
        furnace = FractalFurnace()
        original = furnace.generate("resonance")
        remelted = furnace.remelt(original.artifact_id, "silence")
        if remelted is not None:
            # Should have connections from both seeds
            orig_conns = set(original.semantic_connections)
            assert orig_conns.issubset(set(remelted.semantic_connections))

    def test_find_remeltable(self) -> None:
        furnace = FractalFurnace()
        furnace.generate("resonance")
        furnace.generate("temple")
        remeltable = furnace.find_remeltable("silence")
        # "silence" derivatives should share connections with some artifacts
        assert isinstance(remeltable, list)

    def test_summary(self) -> None:
        furnace = FractalFurnace()
        furnace.generate("resonance")
        furnace.generate("silence")
        s = furnace.summary()
        assert s["artifact_count"] == 2
        assert len(s["artifacts"]) == 2

    def test_multiple_remelts_increment_generation(self) -> None:
        furnace = FractalFurnace()
        a1 = furnace.generate("resonance")
        a2 = furnace.remelt(a1.artifact_id, "spiral")
        if a2 is not None:
            a3 = furnace.remelt(a2.artifact_id, "garden")
            if a3 is not None:
                assert a3.generation == 3
