"""Certifying a model against extracted claims (the pipeline's oracle-to-certificate glue).

Given a runnable model (SBML), the paper it came from, and the claims extracted from that paper,
this runs each claim under the pinned engine, derives the claimed quantity, judges it against the
reported value with the oracle, and assembles a certificate. It is the reusable form of the
metformin worked example: the same machinery that produced one certificate produces any, driven
by a list of :class:`Claim` specs.

A claim that reproduces only because of a load-bearing assumption is marked ``assumption_qualified``
so the certificate cannot round it up. A claim expected to possibly fall short must carry its
root-cause :class:`~reprolith.oracle.Attribution`; the oracle refuses a bare non-pass verdict.

Uses the optional ``engine`` extra (COPASI to run, libsbml to apply parameter overrides).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from .certificate import build_certificate
from .digitization import DIGITIZED_BY
from .engine import final_state, simulate
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    ComparisonMethod,
    FailureMode,
    Fault,
    PercentileBand,
    ReferenceKind,
    Tolerance,
    default_tolerance,
    judge_curve,
    judge_distribution,
    judge_estimation,
    judge_scalar,
    not_evaluable,
    undetermined_shortfall,
)


def _reading_required(
    reference_kind: ReferenceKind,
    digitizer: str,
    what: str,
    *,
    judged: bool = True,
    source_location: str = "",
) -> None:
    """Refuse a claim that takes the figure band without naming what read the figure.

    The figure band is wide on purpose — three times a printed number's for a scalar, twice for a
    curve — because a value read off a picture carries the digitizer's calibration and the plot's
    pixel resolution on top of whatever the model does. The widening is not escapable in the
    direction that matters: :func:`~reprolith.attach_digitized_values` records a reading as
    ``digitized-figure`` and nothing can record it as a printed number.

    It was escapable in the other direction, which is the one that flatters a reconstruction. A
    claim is a record with a ``reference_kind`` field: writing ``digitized-figure`` beside a value
    cited to a paragraph took a scalar's pass threshold from 5% to 15% with no picture, no tool and
    no reading anywhere behind it, and the certificate then marked it ``[figure-reading]`` and said
    nothing a reader could weigh. So the band now costs what it claims: name the tool that read the
    figure. This is the same fence :class:`EstimationClaim` and :class:`PopulationClaim` already put
    on their ``protocol`` — a verdict that rests on work this glue did not do has to state that
    work.

    A claim whose source location already states the reading satisfies this without repeating it:
    :func:`~reprolith.attach_digitized_values` writes the figure, the tool and what the reading cost
    into the citation, and :data:`~reprolith.digitization.DIGITIZED_BY` is the phrase both sides
    agree that statement is made in. So the join needs no extra field, and a record typed by hand
    has to say what read the figure.

    ``judged`` is false for a claim carrying no reference, and then nothing is required. Such a
    claim abstains: ``digitized-figure`` there is the dossier's own marking that the document plots
    a curve and never says what it showed, and the wider band is never consulted because there is
    nothing to consult it against. Demanding a digitizer for a reading nobody took would refuse the
    honest abstention this repository exists to publish.
    """
    stated = bool(digitizer.strip()) or DIGITIZED_BY in source_location
    if judged and reference_kind is ReferenceKind.DIGITIZED_FIGURE and not stated:
        raise ValueError(
            f"{what} is judged in the digitized-figure band, which is wider than a printed "
            "number's, and states no digitizer: name the tool that read the figure (the same "
            "'WebPlotDigitizer 4.7' a digitization file carries), or record the value as the "
            "printed number it is"
        )


def _cited_source(source_location: str, reference_kind: ReferenceKind, digitizer: str) -> str:
    """The source a certificate cites, carrying the reading where the claim states one.

    A reading that came through the join already says this — `attach_digitized_values` writes the
    figure, the tool and what the reading cost into the source location — so the tool is appended
    only where the citation does not already carry it, rather than printed twice.

    "Already carries it" is :data:`~reprolith.digitization.DIGITIZED_BY`, the same predicate
    :func:`_reading_required` accepts the citation on. Asking whether the digitizer's *name* appears
    is a different question with a different answer — a tool called "4.7", or a citation that
    happens to contain it, would silently suppress the statement — and the two would then disagree
    about what stating a reading is.
    """
    if reference_kind is not ReferenceKind.DIGITIZED_FIGURE or not digitizer.strip():
        return source_location
    if DIGITIZED_BY in source_location:
        return source_location
    return f"{source_location} (read off the figure with {digitizer.strip()})"


@dataclass(frozen=True)
class Claim:
    """A published scalar claim to check: a quantity, where to read it, and its reported value.

    ``species`` is the model output to read; ``metric`` derives the scalar from that output's
    time course (``cmax`` peak, ``auc`` area, or ``final`` end value). ``parameter_overrides``
    set the claim's protocol (e.g. a dose) before running. ``assumption_qualified`` marks a
    claim whose reproduction rests on a load-bearing assumption; ``shortfall`` supplies the
    root cause a non-pass verdict requires.
    """

    claim_id: str
    quantity: str
    species: str
    reported: float
    source_location: str
    metric: str = "cmax"
    parameter_overrides: tuple[tuple[str, float], ...] = ()
    #: Prior administrations, as ``(duration, overrides)`` segments run in order before the arm
    #: this claim reports. Each segment runs the author's own model with its own parameter values,
    #: starting from the state the previous one ended in, so the model's own dosing machinery
    #: administers every dose — nothing is added to the model. The claim is read over the **last**
    #: segment; the ones before it condition the state it starts from. Empty for the ordinary
    #: single-administration claim, and mutually exclusive with ``parameter_overrides``, which is
    #: the one-segment spelling of the same thing.
    schedule: tuple[tuple[float, tuple[tuple[str, float], ...]], ...] = ()
    tolerance: Tolerance | None = None
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC
    #: The tool that read the figure, required when ``reference_kind`` is ``digitized-figure``.
    #: See :func:`_reading_required` for why the wider band is not free.
    digitizer: str = ""
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)

    @property
    def cited_source(self) -> str:
        """The source a certificate cites for this claim, carrying the reading behind it."""
        return _cited_source(self.source_location, self.reference_kind, self.digitizer)

    def __post_init__(self) -> None:
        _reading_required(
            self.reference_kind, self.digitizer, f"claim '{self.claim_id}'",
            source_location=self.source_location,
        )
        if self.schedule and self.parameter_overrides:
            raise ValueError(
                "a claim states either a schedule or parameter overrides, not both: the "
                "overrides are the one-segment spelling, and carrying both leaves it unsaid "
                "which segment they belong to"
            )
        if self.schedule and any(duration <= 0.0 for duration, _ in self.schedule):
            raise ValueError("every segment of a dosing schedule must run for a positive time")

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Claim:
        """Build a claim from a plain dict (a claims-dataset record).

        ``parameter_overrides`` may be given as a ``{name: value}`` mapping; ``reference_kind``
        as its string value. ``tolerance`` is still not parsed here — a dataset claim is judged at
        the documented class default.

        ``shortfall`` is, because a dataset claim that does *not* reproduce is no longer
        hypothetical. Without it such a claim reaches ``undetermined_shortfall`` and publishes
        "cause uncategorized, fault with the reconstruction" — which is the honest answer when
        nobody has diagnosed the miss, and a false one when somebody has. The metformin
        twice-daily entry has two: a tissue the deposited model runs too short a protocol to
        reach, and a table cell whose value contradicts its own row.
        """
        overrides = record.get("parameter_overrides", {})
        return cls(
            claim_id=record["claim_id"],
            quantity=record["quantity"],
            species=record["species"],
            reported=float(record["reported"]),
            source_location=record["source_location"],
            metric=record.get("metric", "cmax"),
            parameter_overrides=tuple((k, float(v)) for k, v in overrides.items()),
            schedule=tuple(
                (float(segment["duration"]), tuple(
                    (k, float(v)) for k, v in (segment.get("parameter_overrides") or {}).items()
                ))
                for segment in record.get("schedule", ())
            ),
            reference_kind=ReferenceKind(record.get("reference_kind", "numeric")),
            digitizer=str(record.get("digitizer", "")),
            assumption_qualified=bool(record.get("assumption_qualified", False)),
            shortfall=_shortfall_from(record.get("shortfall")),
        )


def _shortfall_from(record: dict[str, Any] | None) -> Attribution | None:
    """A claim record's stated root cause, or ``None`` when it states none.

    Refuses an incomplete one rather than filling a default: a half-written attribution publishes
    a cause nobody chose, which is worse than the honest `undetermined_shortfall` a missing one
    falls back to.
    """
    if not record:
        return None
    missing = sorted({"mode", "implicated", "fault"} - set(record))
    if missing:
        raise ValueError(
            f"a claim's shortfall states {', '.join(sorted(record))} and needs "
            f"{', '.join(missing)} as well: a root cause is a category, the element it implicates, "
            "and whose fault it looks like"
        )
    return Attribution(
        mode=FailureMode(record["mode"]),
        implicated=str(record["implicated"]),
        fault=Fault(record["fault"]),
    )


def _metric(times: Sequence[float], values: Sequence[float], metric: str) -> float:
    if metric == "cmax":
        return max(values)
    if metric == "final":
        return values[-1]
    if metric == "auc":
        return sum(
            (values[i] + values[i + 1]) / 2.0 * (times[i + 1] - times[i])
            for i in range(len(values) - 1)
        )
    raise ValueError(f"unknown metric {metric!r} (use cmax, auc, or final)")


def _run_protocol(
    *,
    duration: float,
    steps: int,
    read: str,
    overrides: tuple[tuple[str, float], ...] = (),
    overwritten: tuple[str, ...] = (),
    prior: tuple[tuple[float, tuple[tuple[str, float], ...]], ...] = (),
) -> str:
    """Describe the run a time-course judgment rests on, for the certificate's protocol field.

    A simulated number is a function of four things, and the protocol names all four: the window it
    was run over, how finely it was sampled, what was read out of the trajectory, and any parameter
    the claim moved. A metric read off a vanishingly short run is the initial condition; an AUC and
    a curve distance both move with the sample count; and two claims on one model that read a
    different species — or the same species by peak rather than by area — are otherwise identical
    here while disagreeing about the answer.

    Values are written at full precision rather than rounded for display: a reader who re-runs with
    the printed number has to get the number that was run, and six significant figures is enough to
    print two distinct doses identically.

    The observable is written in SBML's concentration notation, ``[X]``, because that is what is
    read: :func:`reprolith.engine.simulate` takes the engine's concentration data. A bare ``X`` is
    the *amount* to anyone who resolves the symbol the way SBML defines it, and on the one committed
    model with real compartments the two differ by 2247x — the metformin certificate's 6.07 nmol/mL
    against 13,630.8 nmol. The same ambiguity had already produced a real cross-engine defect, where
    it was harmless only because every other committed model has a compartment of size 1.
    """
    stated = f"duration={duration!r}, steps={int(steps)}, read={read}"
    if overrides:
        stated += ", overrides: " + ", ".join(f"{name}={value!r}" for name, value in overrides)
    if prior:
        # A prior administration changes the state the reported window starts from, so a reader
        # who re-runs the window alone gets a different number. It is part of the protocol for
        # exactly the reason the window and the sample count are.
        # Consecutive identical administrations are collapsed to a count. Six repetitions of the
        # same clause is not a record a person reads: the El Messaoudi arm's protocol ran to six
        # copies of "12.0 at Metformin_Dose_in_Lumen_in_mg=389.93", and the fact a reader needs
        # from it — six doses, twelve hours apart, all the same — is the one the repetition
        # buries. Only *identical adjacent* segments collapse, so nothing that differs is merged.
        runs: list[tuple[int, float, tuple[tuple[str, float], ...]]] = []
        for segment_duration, segment_overrides in prior:
            if runs and runs[-1][1:] == (segment_duration, segment_overrides):
                count, *rest = runs[-1]
                runs[-1] = (count + 1, *rest)  # type: ignore[assignment]
            else:
                runs.append((1, segment_duration, segment_overrides))
        stated += "; preceded by " + "; ".join(
            (f"{count} x " if count > 1 else "")
            + f"{segment_duration!r} at "
            + (", ".join(f"{name}={value!r}" for name, value in segment_overrides) or "no override")
            for count, segment_duration, segment_overrides in runs
        )
    if overwritten:
        stated += "; " + "; ".join(overwritten)
    return stated


def _events_overwriting(sbml: str, overrides: tuple[tuple[str, float], ...]) -> tuple[str, ...]:
    """Warnings for overrides an event assignment may overwrite during the run.

    An override that cannot reach the run is refused outright (:func:`_apply_overrides`). An event
    is different, and refusing it was measured to be wrong: an event overwrites its target only
    when its trigger fires, so an override still governs the run up to that moment and governs all
    of it when the trigger is never satisfied in the window. Three real shapes each moved the
    answer threefold under a refusal saying the override had no effect.

    What was left was a silence: the certificate published the override and said nothing about the
    event that might replace it. Evaluating the trigger over the protocol window needs the run,
    not a name lookup, so this does not claim the override *was* overwritten — it states that an
    event assigns to the same target and that whether it fires was not evaluated, which is exactly
    what is known. A reader can then check the model; before, there was nothing to check against.
    """
    if not overrides:
        return ()
    # ElementTree, not libSBML. An event assignment names its target in a plain `variable`
    # attribute, so reading it needs no SBML semantics — and routing it through libSBML put a
    # second, needless dependency on a path whose one libSBML entry point (`_apply_overrides`) a
    # caller can already stub. That broke two tests that run on the dependency-free gate, and it
    # would have broken any consumer disclosing a caution without the engine extra installed.
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(sbml)
    except ET.ParseError:
        # Unparseable SBML is the business of the paths that must actually run the model; a
        # disclosure cannot be the thing that reports it, and inventing a caution here would be
        # worse than staying quiet.
        return ()
    targets = {name for name, _ in overrides}
    warnings: list[str] = []
    for index, event in enumerate(
        element for element in root.iter() if _localname(element.tag) == "event"
    ):
        name = event.get("id") or event.get("name") or f"event {index}"
        for assignment in event.iter():
            if _localname(assignment.tag) != "eventAssignment":
                continue
            variable = assignment.get("variable")
            if variable in targets:
                warnings.append(
                    f"caution: event {name!r} assigns to {variable!r}, which this claim overrides "
                    "— whether it fires within the window was not evaluated"
                )
    return tuple(warnings)


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _model_level_math(model: Any) -> list[Any]:
    """Every MathML node outside a kinetic law: rules, initial assignments, event triggers and
    assignments, and constraints. What these read, they read from global scope."""
    nodes = []
    for i in range(model.getNumRules()):
        nodes.append(model.getRule(i).getMath())
    for i in range(model.getNumInitialAssignments()):
        nodes.append(model.getInitialAssignment(i).getMath())
    for i in range(model.getNumConstraints()):
        nodes.append(model.getConstraint(i).getMath())
    for i in range(model.getNumEvents()):
        event = model.getEvent(i)
        nodes.append(event.getTrigger().getMath() if event.getTrigger() else None)
        nodes.append(event.getDelay().getMath() if event.getDelay() else None)
        for j in range(event.getNumEventAssignments()):
            nodes.append(event.getEventAssignment(j).getMath())
    return [node for node in nodes if node is not None]


def _fully_shadowed_ids(model: Any) -> set[str]:
    """Global parameter ids that *every* kinetic law referencing them shadows with its own local.

    Two ways the first attempt at this was wrong. It read `getNumLocalParameters`, which is a
    Level 3 accessor returning 0 on Level 2 — and *all six* committed kinetic models are Level 2,
    including the one whose 135 local parameters the guard was written for, so it saw none of their
    224. The 10 of the corpus's 234 it did see all belong to the Level 3 PK/PD model, which is a
    different class. (This said "five of the six" until a claims audit counted them; the true
    statement is the sharper one.) And it unioned every reaction's locals flatly, so a global shadowed in one
    reaction was refused even where it is the live value in another: the ordinary "global default,
    per-reaction local override" idiom. Measured, that refused an override that moved the answer
    7.4x, under a message stating the opposite.

    So: read the level-agnostic `getParameter`, and refuse only an id that no law anywhere reads
    from the global scope. An id nothing references at all is not shadowed — overriding it is a
    different kind of no-op, and one this function does not claim to catch.
    """
    referencing: dict[str, list[bool]] = {}
    # Everything outside a kinetic law that reads a global reads the *global*, and can never be
    # shadowed by a reaction's local. Counting only kinetic laws meant one reaction declaring a
    # local `k` made a global `k` that a rate rule integrates look fully shadowed: measured, an
    # override of it moved the answer 54.6x and was refused under a message saying it has no
    # effect on the run. Same shape as the 7.4x case the previous round fixed, one route over.
    from .sbml import _libsbml as _sbml_module

    libsbml = _sbml_module()
    # Not `math`: this module now imports the standard library's, and the same shadow already
    # made an `isfinite` call land on an ASTNode once today, in the ingester.
    for expression in _model_level_math(model):
        for name in _symbols_in(libsbml.formulaToString(expression) or ""):
            referencing.setdefault(name, []).append(False)
    for i in range(model.getNumReactions()):
        law = model.getReaction(i).getKineticLaw()
        if law is None:
            continue
        locals_here = {law.getParameter(j).getId() for j in range(law.getNumParameters())}
        formula = law.getFormula() or ""
        for name in locals_here:
            referencing.setdefault(name, [])
        for name in _symbols_in(formula):
            referencing.setdefault(name, []).append(name in locals_here)
    return {name for name, shadows in referencing.items() if shadows and all(shadows)}


def _symbols_in(formula: str) -> set[str]:
    """The bare identifiers a kinetic-law formula mentions."""
    import re

    return set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", formula))


def _apply_overrides(sbml: str, overrides: tuple[tuple[str, float], ...]) -> str:
    from .sbml import _libsbml

    libsbml = _libsbml()  # the typed error that names the extra, not a bare ImportError

    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    # A parameter a rule or an initial assignment determines is recomputed by the solver, so
    # setting its value here changes nothing — and the protocol would then publish an override the
    # run never had. Refused for the same reason an unknown parameter is: an override that does not
    # take is a claim about a run that did not happen.
    # A reaction's kinetic law may declare a local parameter shadowing a global of the same id, and
    # the law reads the local one — so setting the global changes nothing, the run comes back
    # bit-identical, and the protocol publishes an override the run never had. It is the same
    # not-taking override as the two above, by a third route; local parameters are pervasive in
    # real exports (135 in one committed kinetic model), so the shadow is an ordinary shape.
    #
    # An *event* assignment is deliberately not on this list. It looked like the same case and is
    # not: an event overwrites its target only when its trigger fires, so an override still governs
    # the run up to that moment, and may govern all of it if the trigger is never satisfied in the
    # window. Refusing it rejected three measured shapes whose overrides each moved the answer
    # threefold. What remains is a real gap — an override the certificate reports without saying an
    # event may overwrite it — but closing it needs the trigger evaluated over the protocol window,
    # not a name lookup, so it is recorded in docs/findings-note.md rather than guessed at here.
    determined = {
        model.getRule(i).getVariable() for i in range(model.getNumRules())
    } | {
        model.getInitialAssignment(i).getSymbol()
        for i in range(model.getNumInitialAssignments())
    }
    shadowed = _fully_shadowed_ids(model)
    for name, value in overrides:
        parameter = model.getParameter(name)
        if parameter is None:
            raise ValueError(f"parameter {name!r} is not in the model")
        if name in determined:
            raise ValueError(
                f"parameter {name!r} is determined by a rule or initial assignment, so overriding "
                "its value has no effect on the run; override the quantity that determines it"
            )
        if name in shadowed:
            raise ValueError(
                f"parameter {name!r} is shadowed by a kinetic law's own local parameter of the "
                "same id, which is the value that law reads, so overriding the global one has no "
                "effect on the run"
            )
        parameter.setValue(float(value))
    return str(libsbml.writeSBMLToString(document))


def _carry_state_forward(sbml: str, state: Mapping[str, float]) -> str:
    """Set each species' initial amount to the value it held at the end of the previous segment.

    This is how a prior administration is expressed without touching the model's own dosing
    machinery: the next segment is the *same model*, started from where the last one stopped, so
    its dose event fires exactly as the author wrote it. Adding an event instead would be
    reconstruction — a run the artifact does not describe — and would have to be declared as one.

    A species whose initial amount an initial assignment or a rule determines is left alone and
    reported, for the reason `_apply_overrides` refuses the same thing one element type over: SBML
    recomputes it at the start of the run, so writing a value here publishes a starting state the
    segment never held.
    """
    from .sbml import _libsbml

    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    determined = {
        model.getRule(i).getVariable() for i in range(model.getNumRules())
    } | {
        model.getInitialAssignment(i).getSymbol()
        for i in range(model.getNumInitialAssignments())
    }
    recomputed = sorted(name for name in state if name in determined)
    if recomputed:
        raise ValueError(
            "cannot carry the run forward: the model recomputes "
            f"{', '.join(recomputed)} at the start of a run, so the state at the end of the "
            "previous segment would not survive into this one"
        )
    for name, concentration in state.items():
        species = model.getSpecies(name)
        if species is None:
            raise ValueError(f"species {name!r} is not in the model")
        # `simulate` returns COPASI's *concentration* series, and the state variable here is an
        # amount. Writing the concentration straight into `setInitialAmount` divides the carried
        # state by the compartment volume — 2247 mL for this model's venous plasma — which does
        # not fail, does not warn, and makes a prior dose vanish. Measured: it reproduced the
        # no-pre-dose answer exactly, which is what a silently discarded segment looks like.
        compartment = model.getCompartment(species.getCompartment())
        size = compartment.getSize() if compartment is not None and compartment.isSetSize() else None
        if size is None:
            raise ValueError(
                f"species {name!r} lives in compartment {species.getCompartment()!r}, which "
                "states no size, so the amount its concentration stands for is unknown"
            )
        species.setInitialAmount(float(concentration) * float(size))
        species.unsetInitialConcentration()
    return str(libsbml.writeSBMLToString(document))


def _run_schedule(
    sbml: str,
    species: str,
    *,
    # One administration per segment: how long it runs, and the parameter values in force for it.
    # The last is the arm the claim reports; the ones before it condition the state it starts from.
    schedule: Sequence[tuple[float, tuple[tuple[str, float], ...]]],
    steps: int,
    run: Callable[..., tuple[tuple[float, ...], tuple[float, ...]]] = simulate,
    read_final_state: Callable[..., Mapping[str, float]] = final_state,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Run a claim's segments in order and return the *last* segment's time course.

    Each segment runs the author's own model with its own parameter values, starting from the
    state the previous segment ended in. Only the last one is returned, because that is the arm
    the claim reports: the metformin paper's 250 mg validation arm gives the peak after the main
    dose, and the 375 mg pre-dose twelve hours earlier is there to condition it, not to be judged.

    Every species the model declares is carried forward — carrying only the observed one would
    start the next segment with an empty body and every other compartment reset.

    ``run`` is the simulator, so the same segmented run can be driven under a second registered
    engine: corroborating a scheduled claim against the *unscheduled* model would report engine
    agreement about a run the claim never made.

    **Each segment restarts the model's clock**, which is how the dose is administered — the
    author's own event fires again — and is also the limit of the approach. A model carrying a
    second event would fire that one again too, at the same offset into every segment, which is
    not what the author wrote. A time-triggered event is indistinguishable from a dose here, so a
    schedule is refused on a model with more than one rather than guessed at; the metformin models
    carry exactly one, which is the dose.
    """
    from .sbml import _libsbml

    libsbml = _libsbml()
    declared = libsbml.readSBMLFromString(sbml).getModel()
    names = [declared.getSpecies(i).getId() for i in range(declared.getNumSpecies())]
    if len(schedule) > 1 and declared.getNumEvents() > 1:
        raise ValueError(
            f"the model carries {declared.getNumEvents()} events, and each segment of a schedule "
            "restarts its clock — so every one of them fires again in every segment, at the same "
            "offset. That is what administers the dose, and there is no way here to tell a dose "
            "event from an event the author meant to happen once"
        )
    model = sbml
    times: tuple[float, ...] = ()
    values: tuple[float, ...] = ()
    for index, (duration, overrides) in enumerate(schedule):
        segment = _apply_overrides(model, tuple(overrides)) if overrides else model
        times, values = run(segment, species, duration=duration, steps=steps)
        if index + 1 == len(schedule):
            break
        # Read every species' end state and start the next segment from it, from one run rather
        # than one per species: through `simulate` alone that cost twenty-one full simulations for
        # this model and twenty times the wall clock of the run being carried.
        ending = read_final_state(segment, names, duration=duration, steps=steps)
        model = _carry_state_forward(segment, ending)
    return times, values


def _auc_is_established(
    model: str,
    species: str,
    *,
    duration: float,
    steps: int,
    within: float,
    schedule: Sequence[tuple[float, tuple[tuple[str, float], ...]]] = (),
) -> tuple[bool, float]:
    """``(established, relative change)`` for an AUC read off a uniform grid at ``steps``.

    An AUC is a trapezoidal sum over the sample points, so unlike a peak or an end value it is a
    property of the *grid* as well as of the model. On a smooth PK profile that costs nothing —
    the metformin human model's 24-hour AUC agrees to six figures between 240 and 1920 samples.
    On a bolus intravenous profile it costs everything: the same model family in mice gives 658,
    406, 280, 218, 188 and 174 as the sample count doubles from 240 to 7680, still moving 7.9% at
    the last step. A verdict computed on the first of those numbers is a verdict about the grid.

    So the number is measured against itself at twice the resolution, and compared to the *pass*
    tolerance the claim will be judged against. When its own sampling uncertainty is wider than
    the width that separates a pass from a failure, the comparison cannot tell them apart, and
    :func:`certify_model` abstains rather than publishing whichever side of the line it landed on.
    This can only turn a judgment into an abstention, never the reverse.
    """
    if schedule:
        # The claim's own run, not the model's default one. Checking the unscheduled model would
        # measure the convergence of a different integral and report it under this claim — the
        # same "checked the wrong run" shape the corroboration path had, one function over.
        coarse_times, coarse_values = _run_schedule(
            model, species, schedule=schedule, steps=steps
        )
        fine_times, fine_values = _run_schedule(
            model, species, schedule=schedule, steps=steps * 2
        )
    else:
        coarse_times, coarse_values = simulate(model, species, duration=duration, steps=steps)
        fine_times, fine_values = simulate(model, species, duration=duration, steps=steps * 2)
    coarse = _metric(coarse_times, coarse_values, "auc")
    fine = _metric(fine_times, fine_values, "auc")
    scale = max(abs(coarse), abs(fine))
    if not math.isfinite(coarse) or not math.isfinite(fine) or scale == 0.0:
        # Non-finite output is the existing abstention's business, and an AUC of exactly zero has
        # no relative change to measure; neither is this check's to rule on.
        return True, 0.0
    change = abs(fine - coarse) / scale
    return change <= within, change


def certify_model(
    sbml: str,
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[Claim],
    assumptions: Iterable[Assumption] = (),
    gap_report: Sequence[str] = (),
    duration: float,
    steps: int = 480,
) -> Certificate:
    """Run each claim under the pin, judge it, and assemble the certificate.

    The overall verdict is derived by the certificate rule, so a certificate resting on a
    load-bearing assumption cannot report an unqualified ``reproduced``. Each assessment records
    the run behind it — the window, the sample count, and the claim's parameter overrides — so the
    published number can be re-derived from the certificate alone.

    ``gap_report`` carries what the dossier found missing from the *artifact*, which this path
    cannot see for itself: it takes claims and an SBML string, never a dossier. The
    constraint-based class routes its dossier's load-bearing gaps into the certificate, and this
    one did not — so the metformin dossier's load-bearing units gap (45 of 69 extracted values
    state no unit) reached neither the "what was missing" report nor the author's fix list, which
    told that author there were two things to fix where Reprolith's own records held three.
    """
    assessments = []
    for claim in claims:
        if claim.schedule:
            # Prior administrations condition the state; the claim is read over the last segment.
            model = sbml
            times, values = _run_schedule(
                sbml, claim.species, schedule=claim.schedule, steps=steps
            )
            claim_duration = claim.schedule[-1][0]
            claim_overrides = claim.schedule[-1][1]
        else:
            model = (
                _apply_overrides(sbml, claim.parameter_overrides)
                if claim.parameter_overrides else sbml
            )
            times, values = simulate(model, claim.species, duration=duration, steps=steps)
            claim_duration, claim_overrides = duration, claim.parameter_overrides
        predicted = _metric(times, values, claim.metric)
        if claim.metric == "auc":
            # The width the claim will actually be judged against: its own tolerance when it
            # states one, else the documented class default for this comparison.
            pass_width = (
                claim.tolerance
                or default_tolerance(
                    ComparisonMethod.SCALAR_RELATIVE_ERROR, claim.reference_kind
                )
            ).reproduced_within
            established, change = _auc_is_established(
                model, claim.species, duration=claim_duration, steps=steps,
                within=pass_width, schedule=claim.schedule,
            )
            if not established:
                assessments.append(replace(
                    not_evaluable(
                        claim_id=claim.claim_id,
                        quantity=claim.quantity,
                        source_location=claim.cited_source,
                        reason=(
                            f"the AUC moves {change:.1%} between {steps} and {steps * 2} samples, "
                            f"wider than the {pass_width:.1%} that separates a pass from a "
                            "failure here; at this resolution the number is a property of the "
                            "grid, so no verdict is established"
                        ),
                        reference_kind=claim.reference_kind,
                    ),
                    protocol=_run_protocol(
                        duration=claim_duration,
                        steps=steps,
                        read=f"[{claim.species}] {claim.metric}",
                        overrides=claim_overrides,
                        overwritten=_events_overwriting(sbml, claim_overrides),
                        prior=claim.schedule[:-1] if claim.schedule else (),
                    ),
                ))
                continue
        assessment = (
            judge_scalar(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.cited_source,
                reported=claim.reported,
                predicted=predicted,
                reference_kind=claim.reference_kind,
                tolerance=claim.tolerance,
                # A claim that misses carries a cause even when the caller named none, so a
                # shortfall is published as `not-reproduced` instead of raising. Dataset claims
                # never carry one (`Claim.from_record` does not parse it), which made a miss on
                # the blind set a crash rather than the honest verdict it had earned.
                attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
                assumption_qualified=claim.assumption_qualified,
            )
        )
        assessments.append(
            replace(
                assessment,
                protocol=_run_protocol(
                    duration=claim_duration,
                    steps=steps,
                    read=f"[{claim.species}] {claim.metric}",
                    overrides=claim_overrides,
                    overwritten=_events_overwriting(sbml, claim_overrides),
                    prior=claim.schedule[:-1] if claim.schedule else (),
                ),
            )
        )
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
        gap_report=tuple(gap_report),
    )


@dataclass(frozen=True)
class CurveClaim:
    """A published time-course to reproduce: a species curve judged by normalized distance.

    Unlike :class:`Claim` (a scalar metric), the whole trajectory is the claim. ``reference`` holds
    the reported values sampled at the same ``steps + 1`` uniform points over ``[0, duration]`` the
    simulation produces, so the oracle compares like with like. This is the curve counterpart of the
    scalar claim and the natural claim shape for the generic-kinetic class, where the reproducible
    result is the dynamics themselves.
    """

    claim_id: str
    quantity: str
    species: str
    reference: tuple[float, ...]
    source_location: str
    duration: float
    steps: int
    tolerance: Tolerance | None = None
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC
    #: The tool that read the figure, required when ``reference_kind`` is ``digitized-figure``.
    digitizer: str = ""
    parameter_overrides: tuple[tuple[str, float], ...] = ()
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)

    @property
    def cited_source(self) -> str:
        """The source a certificate cites for this claim, carrying the reading behind it."""
        return _cited_source(self.source_location, self.reference_kind, self.digitizer)

    def __post_init__(self) -> None:
        _reading_required(
            self.reference_kind, self.digitizer, f"claim '{self.claim_id}'",
            judged=bool(self.reference), source_location=self.source_location,
        )


def certify_curves(
    sbml: str,
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[CurveClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Run each curve claim under the pin, judge its trajectory, and assemble the certificate.

    The curve counterpart of :func:`certify_model`: it reproduces a whole species time-course with
    the shared curve oracle (:func:`reprolith.judge_curve`) instead of a scalar metric, and builds
    the certificate through the same rule and scope flag. Each claim carries its own ``duration``
    and ``steps``, so the reference and the simulation are sampled at identical points, and both
    are recorded as the assessment's protocol: a curve distance is a function of the grid it was
    measured on, and a window short enough to return the initial condition would otherwise read as
    a perfect reproduction with nothing in the certificate to show it.

    A claim whose ``reference`` is empty abstains rather than being run and judged: there is
    nothing to compare against. That is the ordinary shape of a claim read off a shipped SED-ML
    document, which says which curve the paper plots and never what the figure showed.
    """
    assessments = []
    for claim in claims:
        if not claim.reference:
            # A claim with no reference values has nothing to compare against, so it abstains
            # rather than guessing a pass or a fail (spec: simulation-oracle — "Abstention").
            # This is the ordinary shape of a claim read off a shipped SED-ML document: the
            # document says which curve the paper plots, never what the figure showed. Running
            # the model anyway and judging it against an empty reference used to raise, which
            # turned "no data" into a crash at the one front-end most likely to meet it.
            assessments.append(not_evaluable(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.cited_source,
                reason=(
                    "no reference values for this curve: the source states which curve is "
                    "plotted but not the values it showed, so there is nothing to compare "
                    "the run against"
                ),
                reference_kind=claim.reference_kind,
            ))
            continue
        model = _apply_overrides(sbml, claim.parameter_overrides) if claim.parameter_overrides else sbml
        _, values = simulate(model, claim.species, duration=claim.duration, steps=claim.steps)
        assessment = (
            judge_curve(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.cited_source,
                reference=claim.reference,
                predicted=values,
                reference_kind=claim.reference_kind,
                tolerance=claim.tolerance,
                attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
                assumption_qualified=claim.assumption_qualified,
            )
        )
        assessments.append(
            replace(
                assessment,
                protocol=_run_protocol(
                    duration=claim.duration,
                    steps=claim.steps,
                    read=f"[{claim.species}] curve",
                    overrides=claim.parameter_overrides,
                    overwritten=_events_overwriting(sbml, claim.parameter_overrides),
                ),
            )
        )
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


@dataclass(frozen=True)
class EstimationClaim:
    """A published *parameter estimate* to reproduce by re-fitting from the paper's raw data.

    The estimation counterpart of :class:`Claim`. ``reported`` is the paper's stated estimate and
    ``recovered`` is the estimate Reprolith's re-fit produced; the re-fitting itself — running the
    paper's stated estimation over the shipped raw data — is the deferred, engine-dependent half,
    exactly as the simulator is for a scalar claim, so this glue takes an already-``recovered``
    value. ``shortfall`` supplies the root cause a non-pass estimation verdict requires.

    ``protocol`` records how the estimate was recovered — the objective, the optimizer, the starting
    values, the dataset. A re-fit is sensitive to all four (which is why the estimation tolerance is
    wider than a simulation scalar's), so without them a reader cannot repeat the re-fit, and
    ``recovered == reported`` is an unconditional clean pass with no evidence behind it. The
    ``UNSTATED_ESTIMATION_METHOD`` and ``UNSTATED_STARTING_VALUES`` failure modes name exactly what
    this field carries.
    """

    claim_id: str
    quantity: str
    reported: float
    recovered: float
    source_location: str
    protocol: str
    tolerance: Tolerance | None = None
    assumption_qualified: bool = False
    shortfall: Attribution | None = field(default=None)

    def __post_init__(self) -> None:
        # Refused rather than defaulted: this glue does not run the re-fit, so the protocol is the
        # only evidence on the certificate that one happened at all. Without it a caller can hand
        # in ``recovered == reported`` and publish an unqualified clean estimation pass that no
        # reader can repeat and nothing in the record contradicts.
        if not self.protocol.strip():
            raise ValueError(
                f"estimation claim {self.claim_id!r} states no protocol; an estimate Reprolith "
                "did not re-derive itself is only evidence alongside the objective, optimizer, "
                "starting values, and dataset it came from"
            )


def certify_estimation(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[EstimationClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Assemble a certificate of estimation verdicts (re-fit estimates vs reported estimates).

    The estimation counterpart of :func:`certify_model`: each claim is judged with
    :func:`reprolith.judge_estimation`, so every verdict is recorded at the estimation
    reproduction level and reported separately from simulation. Needs no engine extra — the
    re-derived estimates are supplied, the re-fitter being the deferred half.

    Each assessment carries the claim's estimation ``protocol`` when it states one, because an
    estimation verdict rests on how the re-fit was run as much as on the number it produced.
    """
    assessments = [
        replace(
            judge_estimation(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reported=claim.reported,
                recovered=claim.recovered,
                tolerance=claim.tolerance,
                # The same fallback the simulation front-ends carry: a shortfall the caller
                # did not categorize is published as uncategorized, not raised. Without it
                # this path could emit only a clean pass or a traceback.
                attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
                assumption_qualified=claim.assumption_qualified,
            ),
            protocol=claim.protocol,
        )
        for claim in claims
    ]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=tuple(assumptions),
    )


@dataclass(frozen=True)
class PopulationClaim:
    """A published population figure to reproduce: a percentile envelope over time.

    The population counterpart of :class:`CurveClaim`. ``reported`` and ``predicted`` are the
    paper's and the simulated population's percentile bands (median plus outer percentiles);
    simulating a virtual population is the deferred, engine-and-sampling half, so this glue takes
    the already-``predicted`` bands. ``assumption_qualified`` defaults to ``True`` because a
    population reproduction depends on the reconstructed variability model and the sampling, so its
    verdict is qualified unless the paper fully specifies both.

    ``protocol`` records the sampling the bands came from — how many subjects were simulated and
    under what seed. An envelope's verdict moves with its ensemble size (a correct model reads as
    failed at twenty subjects, and a wrong one passes at a thousand), so without the protocol a
    reader cannot tell a reproduction from a sample size chosen until one appeared. The stochastic
    class records the same thing for the same reason.
    """

    claim_id: str
    quantity: str
    reported: tuple[PercentileBand, ...]
    predicted: tuple[PercentileBand, ...]
    source_location: str
    protocol: str
    tolerance: Tolerance | None = None
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC
    #: The tool that read the figure, required when ``reference_kind`` is ``digitized-figure``.
    digitizer: str = ""
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)

    @property
    def cited_source(self) -> str:
        """The source a certificate cites for this claim, carrying the reading behind it."""
        return _cited_source(self.source_location, self.reference_kind, self.digitizer)

    def __post_init__(self) -> None:
        _reading_required(
            self.reference_kind, self.digitizer, f"claim '{self.claim_id}'",
            judged=bool(self.reported), source_location=self.source_location,
        )
        # Refused rather than defaulted, for the reason an estimation claim's is: this glue does not
        # simulate the population, so the sampling is the only evidence the bands came from a run.
        # An envelope's verdict moves with its ensemble size, so without it a reader cannot tell a
        # reproduction from a subject count chosen until one appeared.
        if not self.protocol.strip():
            raise ValueError(
                f"population claim {self.claim_id!r} states no protocol; bands Reprolith did not "
                "simulate itself are only evidence alongside the number of subjects and the seed "
                "they were drawn under"
            )


def certify_population(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    claims: Iterable[PopulationClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Assemble a certificate of population-envelope verdicts (reported vs simulated bands).

    The population counterpart of :func:`certify_curves`: each claim is judged with
    :func:`reprolith.judge_distribution` — governed by its worst-matched percentile band and
    qualified by default — so a reproduced population figure yields a partially-reproduced
    certificate. Needs no engine extra: the simulated bands are supplied, the population
    simulation being the deferred half.

    Each assessment carries the claim's sampling ``protocol``, because a distributional verdict
    rests on the ensemble that produced the bands as much as on the model — and each qualified
    claim's qualification is written down as an :class:`~reprolith.model.Assumption` naming that
    sampling, so a reader of the certificate can see *what* the flag is qualifying rather than only
    that something was.
    """
    claims = tuple(claims)  # read twice below: once for the assumptions, once for the judgments
    sampling = tuple(
        Assumption(
            id=f"population-sampling-{claim.claim_id}",
            description=(
                "the percentile bands judged here came from a virtual population Reprolith "
                "reconstructed and sampled, not from the paper's own run"
            ),
            chosen=claim.protocol,
            basis=(
                "an envelope's verdict moves with its subject count and seed, and the "
                "between-subject variability model behind it is a reconstruction choice a "
                "manuscript often under-specifies"
            ),
            load_bearing=True,
            alternatives=("a different subject count", "a different sampling seed"),
        )
        for claim in claims
        if claim.assumption_qualified
    )
    assessments = [
        replace(
            judge_distribution(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.cited_source,
                reference=claim.reported,
                predicted=claim.predicted,
                reference_kind=claim.reference_kind,
                tolerance=claim.tolerance,
                # The same fallback the simulation front-ends carry: a shortfall the caller
                # did not categorize is published as uncategorized, not raised. Without it
                # this path could emit only a clean pass or a traceback.
                attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
                assumption_qualified=claim.assumption_qualified,
            ),
            protocol=claim.protocol,
        )
        for claim in claims
    ]
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=assessments,
        assumptions=(*assumptions, *sampling),
    )


__all__ = [
    "Claim",
    "CurveClaim",
    "EstimationClaim",
    "PopulationClaim",
    "certify_curves",
    "certify_estimation",
    "certify_model",
    "certify_population",
]
