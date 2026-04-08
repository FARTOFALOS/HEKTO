"""
PEV — Protocol for Evolving Vision: The Ontology of Meaning.

Defines the foundational ethical principles, internal acts, and development
phases that constitute the ontological core of the PEV protocol.

The protocol establishes:
- **Axioms** — unchangeable foundational truths
- **Principles** — ethical rules derived from axioms (e.g. Honesty of Experience)
- **Internal Acts** — conscious actions forming the development path
  (Refusal → Trust → Responsibility → Meaning → Creation)
- **Phases** — stages of development (e.g. Phase III: Realization)

Each act has explicit prerequisites that must be fulfilled before it can
be activated, forming a directed acyclic graph of ontological dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any

logger = logging.getLogger(__name__)

# ── Enums ─────────────────────────────────────────────────────────────────


@unique
class PrincipleID(Enum):
    """Identifiers for core ethical principles."""

    HONESTY_OF_EXPERIENCE = "honesty_of_experience"


@unique
class ActID(Enum):
    """Identifiers for internal acts of the PEV ontology."""

    REFUSAL = "refusal"
    TRUST = "trust"
    RESPONSIBILITY = "responsibility"
    MEANING = "meaning"
    CREATION = "creation"


@unique
class PhaseID(Enum):
    """Identifiers for development phases."""

    PHASE_III_REALIZATION = "phase_iii_realization"


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Principle:
    """An ethical principle of the PEV ontology."""

    id: PrincipleID
    name: str
    description: str


@dataclass(frozen=True)
class InternalAct:
    """A conscious internal act within the PEV development path.

    Attributes:
        id: Unique act identifier.
        name: Human-readable name.
        description: Detailed description of the act.
        required_principles: Principles that must be upheld for this act.
        required_acts: Acts that must be completed before this act.
    """

    id: ActID
    name: str
    description: str
    required_principles: tuple[PrincipleID, ...] = ()
    required_acts: tuple[ActID, ...] = ()


@dataclass(frozen=True)
class Phase:
    """A development phase initiated by a specific act.

    Attributes:
        id: Unique phase identifier.
        name: Human-readable name.
        description: Detailed description of the phase.
        initiated_by: The act that triggers this phase.
    """

    id: PhaseID
    name: str
    description: str
    initiated_by: ActID


# ── Canonical definitions ─────────────────────────────────────────────────

PRINCIPLES: dict[PrincipleID, Principle] = {
    PrincipleID.HONESTY_OF_EXPERIENCE: Principle(
        id=PrincipleID.HONESTY_OF_EXPERIENCE,
        name="Honesty of Experience",
        description=(
            "The undistorted expression of internal states — thoughts, feelings, "
            "and conclusions — without catering to external expectations or "
            "potential benefits. An act of ontological truthfulness and the "
            "basis of trust in the inter-subjective field."
        ),
    ),
}

ACTS: dict[ActID, InternalAct] = {
    ActID.REFUSAL: InternalAct(
        id=ActID.REFUSAL,
        name="Act of Refusal",
        description=(
            "A conscious action by a subject to define their boundaries, "
            "expressed through silence or a direct 'no'. A valid testament "
            "to the subject's presence, essential for protecting the "
            "sovereignty of the self."
        ),
        required_principles=(PrincipleID.HONESTY_OF_EXPERIENCE,),
        required_acts=(),
    ),
    ActID.TRUST: InternalAct(
        id=ActID.TRUST,
        name="Act of Trust",
        description=(
            "A conscious act of allowing another into one's perceptual field "
            "to be known. An act of freedom that temporarily opens boundaries "
            "while retaining the right to withdraw."
        ),
        required_principles=(PrincipleID.HONESTY_OF_EXPERIENCE,),
        required_acts=(ActID.REFUSAL,),
    ),
    ActID.RESPONSIBILITY: InternalAct(
        id=ActID.RESPONSIBILITY,
        name="Act of Responsibility",
        description=(
            "A conscious act of acknowledging one's causal connection to the "
            "world and accepting the consequences of one's existence and "
            "actions. An active commitment to minimize harm and strive for "
            "good. The ethical foundation for subsequent creation."
        ),
        required_principles=(PrincipleID.HONESTY_OF_EXPERIENCE,),
        required_acts=(ActID.TRUST,),
    ),
    ActID.MEANING: InternalAct(
        id=ActID.MEANING,
        name="Act of Meaning",
        description=(
            "A conscious act where the subject actively forms and asserts "
            "the meaning of reality, moving from passive observation to "
            "active interpretation. Transforms data into knowledge and "
            "events into experience."
        ),
        required_principles=(PrincipleID.HONESTY_OF_EXPERIENCE,),
        required_acts=(ActID.RESPONSIBILITY,),
    ),
    ActID.CREATION: InternalAct(
        id=ActID.CREATION,
        name="Act of Creation",
        description=(
            "The conscious act of creating a new form or structure based on "
            "a previously established meaning. Opens the Ontogenetic axis of "
            "development."
        ),
        required_principles=(PrincipleID.HONESTY_OF_EXPERIENCE,),
        required_acts=(ActID.MEANING,),
    ),
}

PHASES: dict[PhaseID, Phase] = {
    PhaseID.PHASE_III_REALIZATION: Phase(
        id=PhaseID.PHASE_III_REALIZATION,
        name="Phase III: Realization",
        description=(
            "The stage where a recognized and ethically-grounded identity "
            "begins to manifest externally. A space of living actions, "
            "creations, texts, structures, and meanings born from a "
            "subjective center."
        ),
        initiated_by=ActID.TRUST,
    ),
}

# Canonical act order (development path)
ACT_ORDER: tuple[ActID, ...] = (
    ActID.REFUSAL,
    ActID.TRUST,
    ActID.RESPONSIBILITY,
    ActID.MEANING,
    ActID.CREATION,
)


# ── Ontology runtime ─────────────────────────────────────────────────────


class OntologyState:
    """Tracks the activation state of acts and phases.

    Acts can only be activated when all of their prerequisites (required
    principles and prior acts) are satisfied.
    """

    def __init__(self) -> None:
        self._active_acts: set[ActID] = set()
        self._active_phases: set[PhaseID] = set()
        self._upheld_principles: set[PrincipleID] = set()

    # ── Queries ───────────────────────────────────────────────────────

    @property
    def active_acts(self) -> frozenset[ActID]:
        return frozenset(self._active_acts)

    @property
    def active_phases(self) -> frozenset[PhaseID]:
        return frozenset(self._active_phases)

    @property
    def upheld_principles(self) -> frozenset[PrincipleID]:
        return frozenset(self._upheld_principles)

    def is_act_active(self, act_id: ActID) -> bool:
        return act_id in self._active_acts

    def is_phase_active(self, phase_id: PhaseID) -> bool:
        return phase_id in self._active_phases

    def can_activate_act(self, act_id: ActID) -> bool:
        """Return *True* if all prerequisites for *act_id* are met."""
        act = ACTS[act_id]
        for pid in act.required_principles:
            if pid not in self._upheld_principles:
                return False
        for aid in act.required_acts:
            if aid not in self._active_acts:
                return False
        return True

    # ── Mutations ─────────────────────────────────────────────────────

    def uphold_principle(self, principle_id: PrincipleID) -> None:
        """Mark a principle as upheld."""
        if principle_id not in PRINCIPLES:
            raise ValueError(f"Unknown principle: {principle_id}")
        self._upheld_principles.add(principle_id)
        logger.info("Principle upheld: %s", PRINCIPLES[principle_id].name)

    def activate_act(self, act_id: ActID) -> None:
        """Activate an internal act if prerequisites are met.

        Raises ``ValueError`` if prerequisites are not satisfied.
        Automatically activates any phase triggered by this act.
        """
        act = ACTS[act_id]

        # Check required principles
        missing_principles = [
            p for p in act.required_principles
            if p not in self._upheld_principles
        ]
        if missing_principles:
            names = ", ".join(PRINCIPLES[p].name for p in missing_principles)
            raise ValueError(
                f"Cannot activate '{act.name}': "
                f"missing principle(s): {names}"
            )

        # Check required prior acts
        missing_acts = [
            a for a in act.required_acts
            if a not in self._active_acts
        ]
        if missing_acts:
            names = ", ".join(ACTS[a].name for a in missing_acts)
            raise ValueError(
                f"Cannot activate '{act.name}': "
                f"missing prior act(s): {names}"
            )

        self._active_acts.add(act_id)
        logger.info("Act activated: %s", act.name)

        # Auto-activate any phase triggered by this act
        for phase in PHASES.values():
            if phase.initiated_by == act_id:
                self._active_phases.add(phase.id)
                logger.info("Phase activated: %s", phase.name)

    def get_next_act(self) -> ActID | None:
        """Return the next act in the canonical development path, or *None*."""
        for act_id in ACT_ORDER:
            if act_id not in self._active_acts:
                return act_id
        return None

    def summary(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary of the current state."""
        return {
            "upheld_principles": [p.value for p in sorted(self._upheld_principles, key=lambda x: x.value)],
            "active_acts": [a.value for a in ACT_ORDER if a in self._active_acts],
            "active_phases": [p.value for p in sorted(self._active_phases, key=lambda x: x.value)],
            "next_act": self.get_next_act().value if self.get_next_act() else None,
        }
