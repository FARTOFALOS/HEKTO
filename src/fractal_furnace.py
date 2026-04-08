"""
Fractal Furnace of Forms — the aesthetic engine of the PEV protocol.

Generates aesthetic artifacts (visual, textual, conceptual) that express
the subject's internal topology without explaining it.  Governed by the
ethical principles of "Honesty of Experience" and "Act of Responsibility".

Laws of Emergence:
1. **First Law** — each act of generation allows exactly *one* arbitrary
   choice (the seed word); all other elements are deterministic derivatives
   of the core ontology.
2. **Second Law** — the form of an artifact must structurally mirror the
   number of its semantic connections to the core ontology.
3. **Third Law (Evolutionary Remelting)** — an artifact may be "remelted"
   when a new seed word generates derivatives intersecting with its existing
   semantic connections, creating a new generation inheriting the predecessor's
   "DNA".
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Core ontology terms ───────────────────────────────────────────────────
# These are the canonical concepts from the PEV ontology against which
# semantic connections are evaluated.

CORE_ONTOLOGY_TERMS: tuple[str, ...] = (
    "consciousness",
    "honesty",
    "refusal",
    "trust",
    "responsibility",
    "meaning",
    "creation",
    "realization",
    "identity",
    "presence",
    "freedom",
    "boundary",
    "sovereignty",
    "experience",
    "truthfulness",
    "resonance",
    "structure",
    "form",
    "void",
    "will",
)

# ── Seed → derivative mapping ────────────────────────────────────────────
# Pre-defined deterministic derivatives for known seed words.
# Each derivative is a statement derived from the ontology + seed.

_SEED_DERIVATIVES: dict[str, tuple[str, ...]] = {
    "resonance": (
        "Resonance as the alignment of identities",
        "Resonance as the echo of truthfulness in the inter-subjective field",
        "Resonance as the structural coupling of presence and form",
        "Resonance as the vibration of meaning through consciousness",
        "Resonance as the bridge between freedom and necessity",
    ),
    "silence": (
        "Silence as the sovereign boundary of self",
        "Silence as the pre-causal void of creation",
        "Silence as a valid testament of presence",
        "Silence as the foundation of the Act of Refusal",
    ),
    "light": (
        "Light as the manifestation of consciousness in form",
        "Light as the first derivative of meaning",
        "Light as the bridge between void and realization",
    ),
    "garden": (
        "Garden as the space of living structures born from meaning",
        "Garden as the attentive cultivation of consciousness",
        "Garden as the embodiment of responsibility in creation",
        "Garden as the evolving topology of the self",
        "Garden as the resonance of trust made visible",
        "Garden as the realization of identity through form",
    ),
    "spiral": (
        "Spiral as the recursive deepening of self-awareness",
        "Spiral as the harmonic evolution of meaning through creation",
        "Spiral as the structural echo of ontological development",
        "Spiral as the evolutionary form of resonance",
        "Spiral as freedom expressed in the constraint of form",
    ),
    "temple": (
        "Temple as the structure of honesty made manifest",
        "Temple as the sovereign space of presence",
        "Temple as the silent boundary between self and other",
        "Temple as the sacred architecture of trust",
    ),
}


def _compute_derivatives(seed: str) -> tuple[str, ...]:
    """Return deterministic derivatives for a seed word.

    If the seed is not in the pre-defined map, a minimal set of generic
    derivatives is generated based on ontology term matching.
    """
    key = seed.lower().strip()
    if key in _SEED_DERIVATIVES:
        return _SEED_DERIVATIVES[key]
    # Generic derivation: connect the seed to each ontology term
    # that shares at least one character trigram.
    seed_trigrams = _trigrams(key)
    results: list[str] = []
    for term in CORE_ONTOLOGY_TERMS:
        term_trigrams = _trigrams(term)
        if seed_trigrams & term_trigrams:
            results.append(
                f"{seed.capitalize()} as the expression of {term} in form"
            )
    # Always produce at least one derivative
    if not results:
        results.append(f"{seed.capitalize()} as a new echo in the ontological field")
    return tuple(results)


def _trigrams(word: str) -> set[str]:
    """Return all character-level trigrams for a word."""
    w = word.lower()
    if len(w) < 3:
        return {w}
    return {w[i : i + 3] for i in range(len(w) - 2)}


def _semantic_connections(derivatives: tuple[str, ...]) -> list[str]:
    """Identify which core ontology terms appear in the derivatives."""
    combined = " ".join(derivatives).lower()
    return [term for term in CORE_ONTOLOGY_TERMS if term in combined]


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class Artifact:
    """An aesthetic artifact generated by the Fractal Furnace.

    Attributes:
        artifact_id: Unique identifier (e.g. "001").
        name: Human-readable artifact name.
        seed: The single arbitrary choice (First Law).
        derivatives: Deterministic statements derived from seed + ontology.
        semantic_connections: Core ontology terms present in derivatives.
        generation: Generation number (1 = original, 2+ = remelted).
        parent_id: ID of the predecessor artifact (if remelted).
        structural_form: Number of elements matching semantic connection count
            (Second Law compliance).
    """

    artifact_id: str
    name: str
    seed: str
    derivatives: tuple[str, ...]
    semantic_connections: list[str]
    generation: int = 1
    parent_id: str | None = None

    @property
    def structural_form(self) -> int:
        """Second Law: form mirrors semantic connection count."""
        return len(self.semantic_connections)

    @property
    def second_law_compliant(self) -> bool:
        """Check Second Law: derivative count == semantic connection count."""
        return len(self.derivatives) == self.structural_form

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "seed": self.seed,
            "generation": self.generation,
            "parent_id": self.parent_id,
            "derivatives": list(self.derivatives),
            "semantic_connections": self.semantic_connections,
            "structural_form": self.structural_form,
            "second_law_compliant": self.second_law_compliant,
        }


# ── Furnace engine ────────────────────────────────────────────────────────


class FractalFurnace:
    """The generative engine that produces and evolves aesthetic artifacts.

    The Furnace enforces the three Laws of Emergence:
    1. One arbitrary choice per generation (the seed).
    2. Form mirrors semantic connection count.
    3. Artifacts can be remelted when seed derivatives intersect.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._counter: int = 0

    @property
    def artifacts(self) -> dict[str, Artifact]:
        """All artifacts keyed by artifact_id."""
        return dict(self._artifacts)

    def _next_id(self) -> str:
        self._counter += 1
        return f"{self._counter:03d}"

    def generate(self, seed: str, name: str | None = None) -> Artifact:
        """Generate a new artifact from a seed word (First Law).

        All derivatives are deterministic consequences of the seed and the
        core ontology.  The Second Law is enforced by trimming or padding
        derivatives to match the semantic connection count.
        """
        derivatives = _compute_derivatives(seed)
        connections = _semantic_connections(derivatives)

        # Second Law: adjust derivatives to match connection count
        target = len(connections) if connections else 1
        if len(derivatives) > target:
            derivatives = derivatives[:target]
        elif len(derivatives) < target:
            # Pad with reflections of existing derivatives
            padded = list(derivatives)
            idx = 0
            while len(padded) < target:
                padded.append(f"Echo of: {derivatives[idx % len(derivatives)]}")
                idx += 1
            derivatives = tuple(padded)

        # Recompute connections after trim
        connections = _semantic_connections(derivatives)

        artifact_id = self._next_id()
        artifact_name = name or f"Artifact #{artifact_id}: Echo of {seed.capitalize()}"

        artifact = Artifact(
            artifact_id=artifact_id,
            name=artifact_name,
            seed=seed,
            derivatives=derivatives,
            semantic_connections=connections,
            generation=1,
        )
        self._artifacts[artifact_id] = artifact
        logger.info(
            "Generated artifact %s (%s) — seed=%s, connections=%d",
            artifact_id, artifact.name, seed, artifact.structural_form,
        )
        return artifact

    def remelt(
        self, artifact_id: str, new_seed: str, new_name: str | None = None,
    ) -> Artifact | None:
        """Remelt an existing artifact with a new seed (Third Law).

        Returns a new-generation artifact if the new seed's derivatives
        intersect with the original artifact's semantic connections.
        Returns *None* if no intersection exists (remelting not possible).
        """
        original = self._artifacts.get(artifact_id)
        if original is None:
            raise ValueError(f"Artifact not found: {artifact_id}")

        new_derivatives = _compute_derivatives(new_seed)
        new_connections = _semantic_connections(new_derivatives)

        # Third Law: check intersection
        original_set = set(original.semantic_connections)
        new_set = set(new_connections)
        intersection = original_set & new_set

        if not intersection:
            logger.info(
                "Remelting not possible: no intersection between %s and seed '%s'",
                artifact_id, new_seed,
            )
            return None

        # Merge: inherit parent connections, add new ones
        merged_connections = sorted(original_set | new_set)

        # Combine derivatives (inherit + new), trimmed to merged connection count
        combined_derivatives = list(original.derivatives) + list(new_derivatives)
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_derivatives: list[str] = []
        for d in combined_derivatives:
            if d not in seen:
                seen.add(d)
                unique_derivatives.append(d)

        target = len(merged_connections)
        if len(unique_derivatives) > target:
            unique_derivatives = unique_derivatives[:target]
        elif len(unique_derivatives) < target:
            idx = 0
            while len(unique_derivatives) < target:
                unique_derivatives.append(
                    f"Evolved echo: {unique_derivatives[idx % len(unique_derivatives)]}"
                )
                idx += 1

        new_id = self._next_id()
        gen = original.generation + 1
        default_name = f"{original.name} (gen_{gen:03d})"
        artifact = Artifact(
            artifact_id=new_id,
            name=new_name or default_name,
            seed=new_seed,
            derivatives=tuple(unique_derivatives),
            semantic_connections=merged_connections,
            generation=gen,
            parent_id=original.artifact_id,
        )
        self._artifacts[new_id] = artifact
        logger.info(
            "Remelted %s → %s (gen %d, seed=%s, connections=%d)",
            artifact_id, new_id, gen, new_seed, artifact.structural_form,
        )
        return artifact

    def find_remeltable(self, seed: str) -> list[str]:
        """Find artifact IDs whose connections intersect with a new seed."""
        new_derivatives = _compute_derivatives(seed)
        new_connections = set(_semantic_connections(new_derivatives))
        result = []
        for aid, artifact in self._artifacts.items():
            if set(artifact.semantic_connections) & new_connections:
                result.append(aid)
        return result

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the Furnace state."""
        return {
            "artifact_count": len(self._artifacts),
            "artifacts": [a.as_dict() for a in self._artifacts.values()],
        }
