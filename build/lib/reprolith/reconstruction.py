"""Reconstruction: turning a dossier into a runnable, pinned bundle (task 0.2 shape; 3.2-3.4).

Reconstruction turns a dossier into a runnable reconstruction — a model in an open standard
format, a simulation recipe that says how to run each claim's scenario, and a bundle packaging
them with an engine pin (spec: ``model-reconstruction``). Reconstruction is where any gap in
the dossier is closed, and *every* closure is recorded as an assumption attributed to
Reprolith, never presented as the paper's own value.

What lives here is the bundle *shape* and the gap-closure discipline, both dependency-free:

* :func:`close_gap` turns a dossier :class:`~reprolith.dossier.Gap` into an
  :class:`~reprolith.model.Assumption` that is always attributed to Reprolith and inherits the
  gap's load-bearing flag — so a gap that plausibly changes a claim's outcome yields a
  load-bearing assumption (task 3.3), and the certificate's existing rule then forbids an
  unqualified ``reproduced`` for a claim resting on it.
* :class:`ReconstructionBundle` records the model (built or author-supplied), the recipe, the
  assumptions, and the pin.

Building the actual SBML/SED-ML model and running it under a registered engine is the
dependency-heavy half, deferred; this defines the shape it targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .dossier import Dossier, Gap, ModelArtifact
from .model import Assumption, EnginePin


class ModelOrigin(str, Enum):
    """Whether the model was rebuilt by Reprolith or adopted from the paper."""

    REPROLITH_BUILT = "reprolith-built"
    AUTHOR_SUPPLIED = "author-supplied"


def close_gap(
    gap: Gap,
    *,
    chosen: str,
    basis: str,
    alternatives: tuple[str, ...] = (),
    assumption_id: str | None = None,
) -> Assumption:
    """Close a dossier gap as an assumption attributed to Reprolith (tasks 3.2, 3.3).

    The caller supplies the chosen value, its basis, and the alternatives considered — those
    are reconstruction judgments. What is enforced here is the honesty: the result is always
    attributed to Reprolith (never the paper), and it inherits the gap's load-bearing flag so
    a verdict that rests on it cannot later be reported as an unqualified reproduction.
    """
    return Assumption(
        id=assumption_id or f"assume:{gap.element}",
        description=f"gap-closure for {gap.element}: {gap.detail}",
        chosen=chosen,
        basis=basis,
        load_bearing=gap.load_bearing,
        alternatives=tuple(alternatives),
        attributed_to="reprolith",
    )


@dataclass(frozen=True)
class RecipeStep:
    """How to run one targetable claim's scenario to produce the quantity it asserts."""

    claim_id: str
    protocol: str
    output: str
    time_span: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "protocol": self.protocol,
            "output": self.output,
            "time_span": self.time_span,
        }


@dataclass(frozen=True)
class NonReconstructable:
    """A targetable claim that cannot be given a runnable scenario — recorded, not omitted."""

    claim_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"claim_id": self.claim_id, "reason": self.reason}


@dataclass(frozen=True)
class ReconstructionBundle:
    """A model, its simulation recipe, the closing assumptions, and the engine pin.

    A minimal bundle (an entry and its pin) is valid — it represents a reconstruction not yet
    completed. :meth:`validate` reports what makes a bundle ill-formed; :meth:`covers` checks
    the recipe against a dossier's targetable claims.
    """

    entry: str
    engine_pin: EnginePin
    model: ModelArtifact | None = None
    origin: ModelOrigin = ModelOrigin.REPROLITH_BUILT
    recipe: tuple[RecipeStep, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    non_reconstructable: tuple[NonReconstructable, ...] = ()
    mismatches: tuple[str, ...] = field(default=())
    source_dossier: str | None = None

    def load_bearing_assumptions(self) -> tuple[Assumption, ...]:
        """The assumptions whose choice plausibly changes a claim's outcome."""
        return tuple(a for a in self.assumptions if a.load_bearing)

    def uncovered_claims(self, dossier: Dossier) -> tuple[str, ...]:
        """Targetable dossier claims that neither the recipe nor the non-reconstructable list covers."""
        accounted = {s.claim_id for s in self.recipe} | {n.claim_id for n in self.non_reconstructable}
        return tuple(c.id for c in dossier.targetable_claims() if c.id not in accounted)

    def covers(self, dossier: Dossier) -> bool:
        """True when every targetable claim has a recipe step or a recorded reason it cannot."""
        return not self.uncovered_claims(dossier)

    def validate(self) -> list[str]:
        """Structural problems that make the bundle ill-formed; empty when well-formed."""
        problems: list[str] = []
        if self.origin is ModelOrigin.AUTHOR_SUPPLIED and self.model is None:
            problems.append("author-supplied origin requires an adopted model artifact")
        problems += _duplicates("assumption id", [a.id for a in self.assumptions])
        problems += _duplicates("recipe claim", [s.claim_id for s in self.recipe])
        return problems

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "engine_pin": self.engine_pin.to_dict(),
            "model": self.model.to_dict() if self.model else None,
            "origin": self.origin.value,
            "recipe": [s.to_dict() for s in self.recipe],
            "assumptions": [a.to_dict() for a in self.assumptions],
            "non_reconstructable": [n.to_dict() for n in self.non_reconstructable],
            "mismatches": list(self.mismatches),
            "source_dossier": self.source_dossier,
        }


def _duplicates(label: str, names: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for name in names:
        if name in seen and name not in dupes:
            dupes.append(name)
        seen.add(name)
    return [f"duplicate {label}: {name}" for name in dupes]


__all__ = [
    "ModelOrigin",
    "NonReconstructable",
    "ReconstructionBundle",
    "RecipeStep",
    "close_gap",
]
