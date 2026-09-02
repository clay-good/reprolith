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
    #: The unit resolved to its base kinds, when the source's own unit is an identifier rather than
    #: a unit. SBML states units by reference — a parameter reads ``unit_0``, and what that means
    #: lives in a ``unitDefinition`` elsewhere in the file — so recording only the reference gave a
    #: dossier that named a unit without saying what it was, and `unit-mismatch` is a catalogued
    #: failure mode. ``unit`` keeps the source's own wording for provenance; this carries what it
    #: resolves to. ``None`` when the two would be the same, and omitted from ``to_dict`` then, so
    #: a dossier whose units need no resolution is unchanged.
    normalized_unit: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("parameter name is required")
        if not self.unit.strip():
            raise ValueError("a stated unit is required; an unstated unit is a Gap, not a value")
        if not self.source_location.strip():
            raise ValueError("every extracted element must cite its source location")

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source_location": self.source_location,
            "confidence": self.confidence.value,
        }
        if self.normalized_unit is not None:
            record["normalized_unit"] = self.normalized_unit
        return record


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
    """Whether an equation gives a variable's *rate of change*, its *value*, or its *start*.

    The distinction is load-bearing: ``dY/dt = 2X`` and ``Y = 2X`` are different models, so an
    equation that loses its kind on the way through the dossier is rebuilt as a different model
    than the one the source stated. Rate is the default because the dossier's original and
    still most common content is an ODE right-hand side.

    ``INITIAL_ASSIGNMENT`` is the third: it holds only at the start of the run, and after that the
    target keeps whatever the rest of the model does to it. It is not an assignment with a
    narrower window — an assignment recomputed every step and a value set once are different
    models — and it is not a stated value, because SBML makes the target's own ``value``
    attribute inert the moment one exists. The metformin model ships thirty-two of them, and the
    dossier used to record the inert attribute as a quoted parameter for every one.
    """

    RATE = "rate"  # dTarget/dt = expression
    ASSIGNMENT = "assignment"  # target = expression, at all times
    INITIAL_ASSIGNMENT = "initial-assignment"  # target = expression, at the start of the run


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
class DossierReaction:
    """A reaction the artifact's dynamics are written as: what it converts, and how fast.

    A reaction-based model's laws of motion are not equations — they are a stoichiometry and a
    rate law, and the ODE system is derived from them. The dossier used to record neither, so a
    ten-reaction cascade produced state variables, no equations, and a `reaction network` gap
    saying the largest part of the model was not carried. This carries it in the form the artifact
    states it, rather than deriving an ODE the artifact never wrote: the derivation is a choice
    about semantics (concentration or amount, which compartment divides what) and a dossier that
    makes it silently describes a model the paper did not.

    ``local_parameters`` are the kinetic law's own, which SBML lets shadow a global of the same
    name — so they travel with the reaction, not with the model.
    """

    id: str
    rate_expression: str
    source_location: str
    reactants: tuple[tuple[str, float], ...] = ()
    products: tuple[tuple[str, float], ...] = ()
    modifiers: tuple[str, ...] = ()
    local_parameters: tuple[Parameter, ...] = ()
    reversible: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("reaction id is required")
        if not self.rate_expression.strip():
            raise ValueError(
                "a reaction without a rate law states no dynamics; record it as a Gap, not as a "
                "reaction with an empty law"
            )
        if not self.source_location.strip():
            raise ValueError("every extracted element must cite its source location")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rate_expression": self.rate_expression,
            "source_location": self.source_location,
            "reactants": [[name, value] for name, value in self.reactants],
            "products": [[name, value] for name, value in self.products],
            "modifiers": list(self.modifiers),
            "local_parameters": [p.to_dict() for p in self.local_parameters],
            "reversible": self.reversible,
        }


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
    #: The parameters, model components, and upstream assumptions this claim's verdict rests on —
    #: what two claims can *share*, and so the only thing that makes a set of claims more or less
    #: independent evidence than the sum of its members
    #: (see :mod:`reprolith.selection`). Empty means **not characterized**, which is why it is not
    #: derived from the claim's own free text: matching parameter names out of a ``quantity``
    #: string would invent a dependency and then let a selection be defended by it. Naming what a
    #: claim depends on is a modelling judgment, recorded here like every other extracted element.
    footprint: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("claim id is required")
        if not self.source_location.strip():
            raise ValueError("every claim must cite its source location")
        if any(not element.strip() for element in self.footprint):
            raise ValueError(f"{self.id}: a footprint element must name something")

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "id": self.id,
            "quantity": self.quantity,
            "conditions": self.conditions,
            "source_location": self.source_location,
            "targetable": self.targetable,
            "reference_kind": self.reference_kind.value if self.reference_kind else None,
            "reference_data": list(self.reference_data),
        }
        if self.footprint:
            # Omitted when empty so every dossier written before claims carried a footprint keeps
            # its exact bytes, and with them its content digest — the same rule an equation's kind
            # and a gap's `carried_by_artifact` already follow.
            record["footprint"] = sorted(self.footprint)
        return record


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
    #: The reactions the model's dynamics are written as, when it is a reaction network this
    #: ingester can carry. Empty for a rule-based model, and omitted from :meth:`to_dict` then, so
    #: every dossier written before reactions were carried keeps its bytes and its digest.
    reactions: tuple[DossierReaction, ...] = ()
    #: The single compartment a carried reaction network's species live in, when there is one.
    #: A rate law may name it, so rebuilding under a compartment of another name leaves the law
    #: referring to something that is not there.
    compartments: tuple[Parameter, ...] = ()

    def validate(self) -> list[str]:
        """Structural problems that make the dossier ill-formed; empty when well-formed."""
        problems: list[str] = []
        problems += _duplicates("parameter name", [p.name for p in self.parameters])
        problems += _duplicates("initial condition", [p.name for p in self.initial_conditions])
        problems += _duplicates("claim id", [c.id for c in self.claims])
        problems += _duplicates("state variable", list(self.state_variables))
        problems += _duplicates("reaction id", [r.id for r in self.reactions])
        problems += _duplicates("compartment", [c.name for c in self.compartments])
        return problems

    def targetable_claims(self) -> tuple[DossierClaim, ...]:
        """The claims the oracle can actually check."""
        return tuple(c for c in self.claims if c.targetable)

    def load_bearing_gaps(self) -> tuple[Gap, ...]:
        """Gaps whose closure plausibly changes a claim's outcome."""
        return tuple(g for g in self.gaps if g.load_bearing)

    def footprint_vocabulary(self) -> frozenset[str]:
        """Every element name a claim's footprint could anchor to in *this* dossier.

        Parameters, initial conditions, state variables, equation targets, and the gaps
        reconstruction will have to close — the four kinds of thing a claim's verdict rests on that
        a dossier actually records.
        """
        return frozenset(
            [p.name for p in self.parameters]
            + [p.name for p in self.initial_conditions]
            + list(self.state_variables)
            + [e.target for e in self.equations]
            + [g.element for g in self.gaps]
        )

    def unanchored_footprint_elements(self) -> tuple[str, ...]:
        """Footprint names this dossier records nothing for — reported, never refused.

        A dossier adopted from a shipped model file keeps its structure in the artifact rather than
        in extracted equations, so a claim there legitimately rests on a reaction or a compartment
        the dossier never names. Refusing those would make footprints unusable for exactly the
        adopt-and-verify entries that are most of the catalog. They are still worth seeing: an
        unanchored name is one nothing in the dossier can corroborate, so a reader can tell a
        footprint anchored in recorded structure from one that is a bare assertion.
        """
        vocabulary = self.footprint_vocabulary()
        unanchored = {
            element
            for claim in self.claims
            for element in claim.footprint
            if element not in vocabulary
        }
        return tuple(sorted(unanchored))

    def to_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "entry": self.entry,
            "state_variables": list(self.state_variables),
            "equations": [e.to_dict() for e in self.equations],
            "parameters": [p.to_dict() for p in self.parameters],
            "initial_conditions": [p.to_dict() for p in self.initial_conditions],
            "claims": [c.to_dict() for c in self.claims],
            "gaps": [g.to_dict() for g in self.gaps],
            "artifacts": [a.to_dict() for a in self.artifacts],
        }
        if self.reactions:
            record["reactions"] = [r.to_dict() for r in self.reactions]
        if self.compartments:
            record["compartments"] = [c.to_dict() for c in self.compartments]
        return record


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
