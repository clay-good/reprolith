"""The dossier: ingestion's structured, provenance-tagged output (task 0.2 shape; 2.1-2.3).

A dossier is the normalized extraction of a paper's model structure, parameters, protocol,
and — most importantly — the specific published claims a reproduction must target. It is the
sole input to reconstruction, and ingestion never runs a model (spec: ``paper-ingestion``).

The defining honesty rule is made *structural* here: ingestion never silently invents content.
A :class:`Parameter` is by construction an extracted value with a unit, a source, and an
extraction-confidence signal — it cannot hold a missing or unit-less value. A required element
that the source does not state is recorded as a :class:`Gap`, never as a guessed parameter;
guessing is reserved for reconstruction, where it is separately recorded as an assumption. So a
paper with a missing parameter yields a gap, not a value, because the shapes leave no other way
to express it.

This defines the dossier *shape*; extracting one from a real paper is the ingestion stage,
which builds on top of these shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .oracle import ReferenceKind


class ExtractionConfidence(str, Enum):
    """How directly an element came from the source, so scrutiny can be prioritized."""

    QUOTED = "quoted"  # a value read directly from the text/table/figure
    INTERPRETED = "interpreted"  # inferred or interpreted from the source


class GapKind(str, Enum):
    """What kind of required element is missing from the source."""

    PARAMETER = "parameter"
    INITIAL_CONDITION = "initial-condition"
    UNIT = "unit"
    EQUATION = "equation"
    DOSING = "dosing"
    MEDIUM = "medium"  # constraint-based: an unstated exchange/medium bound (load-bearing)
    UPDATE_SCHEME = "update-scheme"  # logical: an unstated synchronous/asynchronous scheme (load-bearing)
    SAMPLING = "sampling"  # stochastic: an unstated seed/trajectory-count sampling protocol
    BOUNDARY = "boundary"  # spatial: an unstated spatial domain or boundary condition
    OTHER = "other"


@dataclass(frozen=True)
class Parameter:
    """An extracted parameter or initial condition: a value, its unit, and its provenance.

    A ``Parameter`` always carries a value and a non-empty unit — it exists only for elements
    the source actually states. Anything missing is a :class:`Gap`, not a ``Parameter`` with a
    guessed value.
    """

    name: str
    value: float
    unit: str
    source_location: str
    confidence: ExtractionConfidence = ExtractionConfidence.QUOTED

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("parameter name is required")
        if not self.unit.strip():
            raise ValueError("a stated unit is required; an unstated unit is a Gap, not a value")
        if not self.source_location.strip():
            raise ValueError("every extracted element must cite its source location")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source_location": self.source_location,
            "confidence": self.confidence.value,
        }


@dataclass(frozen=True)
class Gap:
    """A required element the source does not state — recorded, never filled at ingestion.

    ``load_bearing`` marks a gap whose closure plausibly changes a claim's outcome; it is the
    signal reconstruction uses to flag a load-bearing assumption.
    """

    element: str
    kind: GapKind
    detail: str
    load_bearing: bool = False
    #: Whether the shipped model file still carries this element, so adopt-and-verify closes it.
    #: A reaction network the dossier does not record is missing from the *dossier* and present in
    #: the artifact; a medium the paper never stated is missing from both. The gap is equally real
    #: either way — it is what a rebuild-from-dossier loses — but only the second makes a paper
    #: harder to reproduce, and `estimate_difficulty` is asked exactly that question.
    carried_by_artifact: bool = False

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "element": self.element,
            "kind": self.kind.value,
            "detail": self.detail,
            "load_bearing": self.load_bearing,
        }
        if self.carried_by_artifact:
            record["carried_by_artifact"] = True
        return record


class EquationKind(str, Enum):
    """Whether an equation gives a variable's *rate of change* or its *value*.

    The distinction is load-bearing: ``dY/dt = 2X`` and ``Y = 2X`` are different models, so an
    equation that loses its kind on the way through the dossier is rebuilt as a different model
    than the one the source stated. Rate is the default because the dossier's original and
    still most common content is an ODE right-hand side.
    """

    RATE = "rate"  # dTarget/dt = expression
    ASSIGNMENT = "assignment"  # target = expression, at all times


@dataclass(frozen=True)
class Equation:
    """An extracted governing equation for a state variable or observable."""

    target: str
    expression: str
    source_location: str
    kind: EquationKind = EquationKind.RATE

    def to_dict(self) -> dict[str, Any]:
        record = {
            "target": self.target,
            "expression": self.expression,
            "source_location": self.source_location,
        }
        if self.kind is not EquationKind.RATE:
            # Omitted at the default so every dossier written before equations carried a kind
            # keeps its exact bytes, and with them its content digest.
            record["kind"] = self.kind.value
        return record


@dataclass(frozen=True)
class DossierClaim:
    """A concrete published result a reproduction can target — the oracle's checklist.

    A non-targetable result (a schematic figure, a cartoon) is retained with ``targetable``
    false rather than dropped. A targetable claim records whether its reference is numeric data
    or a figure image, so the oracle knows what it must compare against.
    """

    id: str
    quantity: str
    conditions: str
    source_location: str
    targetable: bool = True
    reference_kind: ReferenceKind | None = None
    reference_data: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("claim id is required")
        if not self.source_location.strip():
            raise ValueError("every claim must cite its source location")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "quantity": self.quantity,
            "conditions": self.conditions,
            "source_location": self.source_location,
            "targetable": self.targetable,
            "reference_kind": self.reference_kind.value if self.reference_kind else None,
            "reference_data": list(self.reference_data),
        }


@dataclass(frozen=True)
class ModelArtifact:
    """A model file the paper ships, its detected format, and whether it validates.

    A valid artifact is preserved as a candidate starting point for reconstruction
    (adopt-and-verify), not overwritten.
    """

    filename: str
    detected_format: str
    validates: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "detected_format": self.detected_format,
            "validates": self.validates,
        }


@dataclass(frozen=True)
class Dossier:
    """The structured, provenance-tagged extraction for one catalog entry.

    An empty dossier (only the entry it belongs to) is valid: ingestion may legitimately find
    nothing extractable and record it all as gaps. :meth:`validate` returns the structural
    problems that make a dossier ill-formed (duplicate identifiers), and is empty for a
    well-formed one.
    """

    entry: str
    state_variables: tuple[str, ...] = ()
    equations: tuple[Equation, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    initial_conditions: tuple[Parameter, ...] = ()
    claims: tuple[DossierClaim, ...] = ()
    gaps: tuple[Gap, ...] = ()
    artifacts: tuple[ModelArtifact, ...] = field(default=())

    def validate(self) -> list[str]:
        """Structural problems that make the dossier ill-formed; empty when well-formed."""
        problems: list[str] = []
        problems += _duplicates("parameter name", [p.name for p in self.parameters])
        problems += _duplicates("initial condition", [p.name for p in self.initial_conditions])
        problems += _duplicates("claim id", [c.id for c in self.claims])
        problems += _duplicates("state variable", list(self.state_variables))
        return problems

    def targetable_claims(self) -> tuple[DossierClaim, ...]:
        """The claims the oracle can actually check."""
        return tuple(c for c in self.claims if c.targetable)

    def load_bearing_gaps(self) -> tuple[Gap, ...]:
        """Gaps whose closure plausibly changes a claim's outcome."""
        return tuple(g for g in self.gaps if g.load_bearing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry,
            "state_variables": list(self.state_variables),
            "equations": [e.to_dict() for e in self.equations],
            "parameters": [p.to_dict() for p in self.parameters],
            "initial_conditions": [p.to_dict() for p in self.initial_conditions],
            "claims": [c.to_dict() for c in self.claims],
            "gaps": [g.to_dict() for g in self.gaps],
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


def estimate_difficulty(dossier: Dossier) -> str:
    """Advisory difficulty estimate from a dossier's observable signals (spec: model-catalog).

    Reads the signals the spec names — a runnable model file, parameter/equation completeness,
    and how many gaps (especially load-bearing ones) reconstruction must close:

    * ``low`` — a valid shipped model and no gaps: adopt-and-verify with nothing to assume;
    * ``high`` — a load-bearing gap, or many gaps, or no usable model structure at all;
    * ``medium`` — otherwise.

    A valid shipped model counts as structure: for an adopt-and-verify entry (spec 3.4), including
    every constraint-based dossier, the structure lives in the adopted model file rather than in
    hand-extracted equations, so the estimate must not treat that as "no structure".

    Never a gate: the estimate routes and prioritizes, it does not block a requester.
    """
    has_runnable_model = any(a.validates for a in dossier.artifacts)
    has_structure = bool(dossier.equations or dossier.state_variables) or has_runnable_model
    # A gap the shipped model still carries is closed by running that model, so it does not make
    # the paper harder to reproduce — it makes the dossier a worse standalone description. Counting
    # those collapsed the estimate: once intake began recording the reaction network it reads past,
    # every SBML entry scored `high`, and an estimate that is constant routes nothing.
    outstanding = [g for g in dossier.gaps if not (has_runnable_model and g.carried_by_artifact)]
    load_bearing = [g for g in outstanding if g.load_bearing]
    if load_bearing or len(outstanding) > 3 or not has_structure:
        return "high"
    if has_runnable_model and not outstanding:
        return "low"
    return "medium"


def _duplicates(label: str, names: list[str]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for name in names:
        if name in seen and name not in dupes:
            dupes.append(name)
        seen.add(name)
    return [f"duplicate {label}: {name}" for name in dupes]


__all__ = [
    "Dossier",
    "DossierClaim",
    "Equation",
    "ExtractionConfidence",
    "Gap",
    "GapKind",
    "ModelArtifact",
    "Parameter",
    "estimate_difficulty",
]
