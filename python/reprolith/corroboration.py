"""Cross-engine corroboration: is a curve verdict the model's, or one solver's quirk?

A single simulator can reproduce a paper for the wrong reason — a solver-specific integration
artifact. Running the *same* SBML model under two independently-implemented engines and checking
they produce the same trajectory separates a model's behavior from a single engine's quirks
(spec: ``simulation-oracle`` — engine-sensitivity). When they agree, the verdict is
engine-independent; when they diverge beyond tolerance, the result is **engine-sensitive** and a
verdict resting on one engine should be treated as such (the ``ENGINE_SENSITIVITY`` failure mode).

This uses the pinned COPASI engine and the libRoadRunner engine (CVODE), which share no code, so
agreement is real corroboration. Both are optional: it needs the ``engine`` and ``corroborate``
extras and imports them lazily.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace

from .engine import ENGINE as _COPASI_ENGINE
from .engine import (
    ROADRUNNER_ENGINE,
    engine_version,
    final_state_with_roadrunner,
    roadrunner_version,
    simulate,
    simulate_with_roadrunner,
)
from .model import EnginePin
from .oracle import normalized_curve_distance

#: How far a raw distance is lifted before it is rounded up to a decade. Two: the measured
#: cross-run spread on the model that exposed the problem was about 12%, and a factor of two keeps
#: a value that close to a boundary on the same side of it in every observation, at the cost of at
#: most one decade of looseness in the published bound.
_MARGIN = 2.0


@dataclass(frozen=True)
class EngineCorroboration:
    """The result of running one thing under two engines and comparing what they returned.

    ``quantity`` names what was compared, because it is no longer always a curve: an ODE class
    compares a species trajectory, and the constraint-based class compares a model's optimal
    objective value, which is the one number two LP solvers must agree on even when their flux
    vectors differ.
    """

    quantity: str
    engines: tuple[str, str]
    distance: float
    stable: bool
    #: The installed build of each engine in :attr:`engines`, in the same order — read off the
    #: running libraries, never asserted. A certificate expires when the software that computed it
    #: changes; a corroboration bound carried the same weight and named no software at all, so a
    #: number measured against libRoadRunner 2.7 read as current against any later build. Empty
    #: strings mean the versions were not captured, which is what a record written before this
    #: existed says — and it has to keep saying that rather than borrowing today's.
    versions: tuple[str, str] = ("", "")
    #: How the two answers were compared. A trajectory or an optimum is compared as a *distance*,
    #: which can be small without being zero; an attractor set or a fixed-point set is discrete —
    #: the two implementations either return the same object or they do not, and calling that a
    #: distance of zero would invite reading it as "six orders better than the curve classes" when
    #: it is a different kind of statement entirely. Omitted from the record at the default, so
    #: every record written before this field existed keeps its bytes.
    comparison: str = "normalized-distance"
    #: The tolerance the caller asked for. The verdict is decided on the *published* bound, so the
    #: criterion actually applied is :meth:`effective_criterion` — never looser than this, and up
    #: to five times tighter when this is not itself a power of ten.
    criterion: float = 0.02

    def effective_criterion(self) -> float:
        """The largest decade at or below :attr:`criterion` — what the verdict was really held to."""
        if not math.isfinite(self.criterion) or self.criterion <= 0.0:
            return self.criterion
        return 10.0 ** math.floor(math.log10(self.criterion))

    def summary(self) -> str:
        verdict = "engine-independent" if self.stable else "engine-sensitive"
        if self.comparison == "exact-match":
            agreed = "agree exactly" if self.stable else "do not agree"
            return (
                f"{self.quantity}: {self.engines[0]} vs {self.engines[1]} {agreed} "
                f"-> {verdict}"
            )
        return (
            f"{self.quantity}: {self.engines[0]} vs {self.engines[1]} normalized distance "
            f"at most {self.distance_bound():.0e} against a {self.effective_criterion():.0e} "
            f"criterion -> {verdict}"
        )

    def record(self) -> dict[str, object]:
        """This comparison as the committed record's shared fields, in one place.

        Both milestone scripts assembled these by hand, so a field added to one was missing from
        the other — which is how the published corroboration went years naming no engine build.
        The distance is published as a bound rather than a measurement; see
        :meth:`distance_bound`.
        """
        record: dict[str, object] = {
            "engines": list(self.engines),
            "engine_versions": list(self.versions),
            "distance_at_most": self.distance_bound(),
            "engine_independent": self.stable,
        }
        if self.comparison != "normalized-distance":
            record["comparison"] = self.comparison
        return record

    def distance_bound(self) -> float:
        """The distance rounded *up* to the next power of ten — what is safe to publish.

        The distance between two engines that agree is a difference of nearly-equal numbers, so
        its leading digits are the engines' own last-place noise amplified. COPASI is not
        bit-identical across repeated calls in one process (a period-2 alternation at about 1e-11
        relative, present on four of the six committed kinetic models), and on one of them that
        moved the published distance by 8% — so a five-figure distance in a committed artifact
        reads as a measurement and is not reproducible even on the same machine.

        Rounding up rather than to nearest keeps the number honest under the only reading that
        matters: it never states better agreement than was measured.
        """
        if not math.isfinite(self.distance) or self.distance <= 0.0:
            return self.distance
        # One significant figure was not coarse enough: the distance also moves between machines
        # (a committed 4e-07 bound was exceeded on CI at 4.55e-07, with different engine builds),
        # so the published granularity is the decade. It still says what the number is for —
        # agreement three to five orders below the tolerance — without pretending to digits no
        # second machine reproduces.
        #
        # The decade alone was not enough either, for a distance sitting near a boundary. Measured
        # on the metformin reconstruction: three runs of one milestone script on one machine
        # published 1e-06 twice and 1e-07 once, because the raw distance straddles 1e-07 (1.11e-07
        # in isolation, just under it inside a longer run). A committed number that moves a decade
        # between two runs is the very thing this method exists to prevent. So the distance is
        # lifted by a margin before it is rounded up: a value within a factor of `_MARGIN` of the
        # decade below is published at the decade above, and both draws land on the same number.
        # The change is one-directional by construction — the margin is greater than one, so the
        # published bound can only ever loosen, and it still never states better agreement than
        # was measured.
        return float(f"{10.0 ** math.ceil(math.log10(self.distance * _MARGIN)):.0e}")


def corroborate_curve(
    sbml: str,
    species: str,
    *,
    duration: float,
    steps: int,
    rel_tol: float = 0.02,
    overrides: tuple[tuple[str, float], ...] = (),
    schedule: tuple[tuple[float, tuple[tuple[str, float], ...]], ...] = (),
    draws: int = 2,
) -> EngineCorroboration:
    """Run a species curve under both engines and report whether the verdict is engine-independent.

    Simulates ``species`` over ``[0, duration]`` at ``steps`` intervals under both COPASI and
    libRoadRunner (same grid, so the curves align), then measures their normalized distance. A
    published distance bound at or below ``rel_tol`` means the two independent engines agree — the
    curve is the model's behavior, not one solver's; above it, the result is engine-sensitive and
    should be flagged rather than trusted to a single engine. The criterion is applied to the
    *published* bound rather than the raw distance, so the record and its verdict never disagree.

    ``overrides`` are the parameter values the claim sets before running, in the same
    ``(name, value)`` form a certified claim carries — and they are applied through the same
    function certification uses, so an override that would not take effect is refused here too. A
    claim that runs at a non-default dose is otherwise uncorroborable: without them, the only arm
    a model's curves can be checked on is its default one, which for the metformin reconstruction
    is one of its two claims.

    ``schedule`` is the claim's prior administrations, when it has them. It replaces ``overrides``
    rather than joining them — the schedule's last segment carries the claim's own values — and
    both engines walk the same segments, carrying state forward the same way.

    ``draws`` is how many times the comparison is measured, and the **worst** distance is the one
    reported. Two, because COPASI's non-determinism is a period-two alternation within one
    process, so two consecutive draws sample both phases and a third adds nothing.

    This is what makes a published bound reproducible, and it replaces an argument that did not
    hold. ``distance_bound`` lifts a distance by a fixed margin before rounding up to a decade, so
    that two draws either side of a decade boundary land on the same number — but a fixed margin
    only relocates the unlucky case. Measured on this model's muscle curve: the two phases are
    4.89e-08 and 5.53e-08, a 13% spread, and the margin of two lifts them to 9.79e-08 and 1.11e-07
    — either side of 1e-07. Three regenerations of the PK/PD milestone on one machine, with
    identical code and identical engine builds, published 1e-06, then 1e-07, then 1e-06 for that
    claim. Taking the worst of two draws published 1e-06 six times out of six.

    It is one-directional, like the margin it backs up: the worst of several measurements can only
    ever state *weaker* agreement than a single one, never better, so it cannot turn an
    engine-sensitive result into an engine-independent one.
    """
    if draws < 1:
        raise ValueError(f"a corroboration needs at least one draw, not {draws!r}")
    if overrides and not schedule:
        # Applied once, outside the draw loop: it rewrites the model text, and re-applying it to
        # an already-overridden model is work every draw would repeat.
        from .certify import _apply_overrides

        sbml = _apply_overrides(sbml, overrides)

    def measure() -> float:
        """One comparison of the two engines on this run."""
        if schedule:
            # A claim with prior administrations is a different run from the model's default arm,
            # and corroborating the default one would publish engine agreement about a run the
            # claim never made — with the claim's id on it. Both engines walk the same segments.
            from .certify import _run_schedule

            _, copasi = _run_schedule(sbml, species, schedule=schedule, steps=steps)
            _, roadrunner = _run_schedule(
                sbml, species, schedule=schedule, steps=steps,
                run=simulate_with_roadrunner,
                # Its own end state too: reading it with COPASI would make the corroborated run
                # half COPASI, and a corroboration that shares half its arithmetic with the thing
                # it is corroborating is not one.
                read_final_state=final_state_with_roadrunner,
            )
        else:
            _, copasi = simulate(sbml, species, duration=duration, steps=steps)
            _, roadrunner = simulate_with_roadrunner(
                sbml, species, duration=duration, steps=steps
            )
        return normalized_curve_distance(copasi, roadrunner)

    distance = max(measure() for _ in range(draws))
    result = EngineCorroboration(
        quantity=species,
        engines=(_COPASI_ENGINE, ROADRUNNER_ENGINE),
        distance=distance,
        stable=False,
        # Read off the libraries that just produced these two trajectories, after they ran, so the
        # record names the builds the number came from rather than what was declared anywhere.
        versions=(engine_version(), roadrunner_version()),
    )
    # The verdict answers to the number that is published, not the one that was measured. The
    # artifact records the distance rounded *up* to the next decade, so a raw 0.011 was published
    # as "at most 1e-01 -> engine-independent" against a 0.02 criterion — a record that contradicts
    # itself on its face. Judging the bound keeps the two in step and errs toward engine-sensitive.
    # It also means the criterion actually applied is the largest decade at or below ``rel_tol``
    # (0.01 for the 0.02 default), which is up to five times tighter than the number passed in —
    # so it is reported rather than left for a reader to derive. Every committed model measures at
    # most 1e-03, three orders inside even the tightened criterion.
    return replace(result, stable=result.distance_bound() <= rel_tol, criterion=rel_tol)


#: What the second implementation is called in a committed record. Named here rather than at the
#: call site for the same reason the engine constants are: the record is keyed by these strings,
#: and a record naming a different spelling of one tool reads as a different tool.
COBRAPY_ENGINE = "cobrapy"


def _cobrapy_objective(sbml: str) -> tuple[float, str]:
    """COBRApy's optimum for this model, and the build that produced it.

    Imported lazily, like every other optional engine here: the core stays dependency-free and a
    missing extra has to fail by name rather than at import time.
    """
    import tempfile

    import cobra  # a different reader and a different LP backend, which is what makes this evidence

    with tempfile.NamedTemporaryFile("w", suffix=".xml", encoding="utf-8") as handle:
        # COBRApy reads a path, not a string. The file is this process's own and is removed on
        # exit; nothing about the comparison depends on where it sat.
        handle.write(sbml)
        handle.flush()
        model = cobra.io.read_sbml_model(handle.name)
    value = model.slim_optimize(error_value=None)
    if value is None:
        raise ValueError(
            "cobrapy found no optimum for this model, so there is no second number to compare; "
            "that is a disagreement about whether the program is solvable rather than a distance"
        )
    return float(value), str(cobra.__version__)


def corroborate_objective(sbml: str, *, rel_tol: float = 1e-6) -> EngineCorroboration:
    """Solve one constraint-based model under two independent implementations and compare.

    The constraint-based class had no second registered engine, so the corroboration surface
    reported it as *unchecked* — an absence, correctly, and not one that had to stay. COBRApy is a
    different implementation of the same problem (a different LP backend behind a different model
    reader), so agreement between it and Reprolith's own solver is real corroboration of the same
    kind the ODE classes already publish.

    **What is compared is the objective value, and that is the point rather than a shortcut.** A
    linear program's optimum is unique; the flux vector that attains it usually is not. Comparing
    flux distributions would report disagreement wherever a model has alternate optima — which is
    most of them — and call two correct solvers engine-sensitive. So this compares the one quantity
    both must agree on, and the certificate's own claim is that value.

    The distance is the relative difference between the two optima, which puts it on the same
    scale as the curve comparison's normalized distance and through the same published-bound rule.
    An infeasible model under either solver is not a disagreement about a number, so it raises —
    ``InfeasibleFba`` from this side, and a stated error from COBRApy's — rather than being
    reported as a distance. A published "engine-sensitive" would say the two disagreed about a
    value, when what happened is that one of them found no value at all.

    Needs the ``fba`` extra (Reprolith's own solver) and the ``corroborate`` extra (COBRApy).
    """
    from .fba import solve_objective, solver_pin
    from .sbml import ingest_fbc_sbml

    model = ingest_fbc_sbml(sbml)
    mine = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    theirs, cobrapy_version = _cobrapy_objective(sbml)
    scale = max(abs(mine), abs(theirs))
    distance = 0.0 if scale == 0.0 else abs(mine - theirs) / scale
    pin = solver_pin()
    result = EngineCorroboration(
        quantity="maximal objective value",
        engines=(pin.engine, COBRAPY_ENGINE),
        distance=distance,
        stable=False,
        # Read off the two libraries that just solved these programs, after they ran.
        versions=(pin.version, cobrapy_version),
    )
    return replace(result, stable=result.distance_bound() <= rel_tol, criterion=rel_tol)


def _reprolith_build(pin: EnginePin) -> str:
    """The build string for a side of the comparison that *is* Reprolith.

    Not the package version. Every other engine here reports a version that moves when its code
    does — COPASI's, libRoadRunner's, scipy's, COBRApy's — and Reprolith's has been 0.0.1
    throughout, so a record naming it says nothing about which code produced the agreement and
    cannot be told from one written a hundred commits ago. The pin's algorithm string is what
    carries the path taken *and* the revision of the code that took it, which is the same thing a
    certificate's freshness check reads.
    """
    return pin.algorithm or pin.version


#: The independent Boolean-network library the logical class is corroborated against. Named here
#: for the same reason the others are: the record is keyed by these strings.
CANA_ENGINE = "cana"
#: The independent SAT implementation the large logical models' fixed points are corroborated
#: against. Reprolith's own scalable path is z3; sympy's DPLL shares no code with it.
SYMPY_ENGINE = "sympy-sat"


def _cana_signature(rules: Mapping[str, str]) -> tuple[tuple[int, tuple[int, ...]], str]:
    """CANA's synchronous attractor signature for these rules, and the build that produced it.

    The rule text is handed to CANA's own parser rather than to a truth table Reprolith computed:
    a comparison in which one side is told what the model does by the other side is not a
    comparison. The transliteration is operators only — ``!``/``&``/``|`` to ``not``/``and``/``or``
    — because CANA evaluates the condition as Python.

    The signature is the attractor **count and periods**, not the state sets: CANA reduces
    constant nodes, so its states are not always over the same variables, while the count and
    periods are invariant to that reduction. That is the same comparison this class's committed
    cross-validation uses, for the same reason.
    """
    import cana
    from cana.boolean_network import BooleanNetwork

    lines = ["# BOOLEAN RULES"]
    for node, rule in rules.items():
        lines.append(
            f"{node}*=" + rule.replace("!", " not ").replace("&", " and ").replace("|", " or ")
        )
    network = BooleanNetwork.from_string_boolean("\n".join(lines))
    attractors = network.attractors()
    signature = (len(attractors), tuple(sorted(len(cycle) for cycle in attractors)))
    return signature, str(getattr(cana, "__version__", "unknown"))


def corroborate_attractors(rules: Mapping[str, str]) -> EngineCorroboration:
    """Enumerate one Boolean network's attractors under Reprolith and under CANA, and compare.

    The logical class had no second registered engine, so its verdicts were reported as
    un-corroborated — while an independent implementation of exactly this question was already
    installed here to generate the class's committed cross-validation references. The difference
    between those references and this is *when*: a committed reference says the two tools agreed
    once, on the rules as they were then; corroboration re-runs both now and publishes what the
    second one said about the model this certificate is about.

    Discrete, not a distance: two attractor enumerations of the same synchronous network are the
    same object or they are not.

    Needs the ``corroborate`` extra (CANA), and is bounded by exact enumeration on both sides —
    the large signalling models are corroborated on their fixed points instead
    (:func:`corroborate_fixed_points`).
    """
    from .logical import parse_boolean_network, solver_pin_for

    mine = parse_boolean_network(dict(rules)).attractors()
    signature = (len(mine), tuple(sorted(len(cycle) for cycle in mine)))
    theirs, cana_version = _cana_signature(rules)
    pin = solver_pin_for(nodes=len(rules))
    return EngineCorroboration(
        quantity=f"{len(rules)}-node synchronous attractor set",
        engines=(pin.engine, CANA_ENGINE),
        distance=0.0 if signature == theirs else 1.0,
        stable=signature == theirs,
        versions=(_reprolith_build(pin), cana_version),
        comparison="exact-match",
    )


def _complete_assignment(
    solution: Mapping[object, object], rules: Mapping[str, str]
) -> frozenset[tuple[str, int]]:
    """One satisfying model as a full state, refusing a partial one rather than comparing it.

    A DPLL search returns the assignment it needed, which may leave a variable undecided. Such a
    model is a *set* of states, not one, and silently comparing it against a complete state makes
    the two sides differ for a reason that has nothing to do with the network — publishing "these
    steady states are solver-dependent" about a model whose steady states both tools agree on.
    """
    assignment = {str(symbol): int(bool(value)) for symbol, value in solution.items()}
    missing = sorted(set(rules) - set(assignment))
    if missing:
        raise ValueError(
            "the independent solver returned a model that leaves "
            f"{len(missing)} node(s) undecided ({', '.join(missing[:5])}"
            f"{'…' if len(missing) > 5 else ''}), so it describes a set of states rather than "
            "one; comparing it against a complete state would report a disagreement that is "
            "about the answer's shape and not about the network"
        )
    return frozenset(assignment.items())


def corroborate_fixed_points(rules: Mapping[str, str]) -> EngineCorroboration:
    """Enumerate one Boolean network's fixed points under Reprolith and under sympy, and compare.

    This is the large-network half. Reprolith solves ``xᵢ ⟺ ruleᵢ(x)`` with z3 and enumerates the
    solutions with blocking clauses; sympy's DPLL implementation shares no code with z3, so the two
    agreeing on the *set* of steady states — every state, not a count — is real corroboration of
    the answer a 60-node model's certificate rests on, where 2ⁿ enumeration is impossible for
    either of them.

    The state sets are compared rather than their sizes, which means both sides have to describe
    the same variables — checked rather than assumed, because a satisfiability search may return a
    *partial* model, leaving a variable its search never had to decide. Compared against a complete
    state that is unequal, and the artifact would then report a model's certified steady states as
    solver-dependent when what differed was the shape of one answer. It is refused by name
    instead: a disagreement Reprolith cannot attribute to the model is not a finding about the
    model.

    Needs the ``sat`` extra (z3, Reprolith's own path) and the ``corroborate`` extra (sympy).
    """
    import sympy

    from .logical import parse_boolean_network, solver_pin_for

    network = parse_boolean_network(dict(rules))
    mine = {frozenset(state.items()) for state in network.fixed_points()}
    symbols = {node: sympy.Symbol(node) for node in rules}
    condition = sympy.And(*[
        sympy.Equivalent(symbols[node], sympy.sympify(rule.replace("!", "~"), locals=symbols))
        for node, rule in rules.items()
    ])
    theirs = set()
    for solution in sympy.logic.inference.satisfiable(condition, all_models=True):
        if not solution:
            continue  # sympy yields a single falsey model when there is no solution at all
        theirs.add(_complete_assignment(solution, rules))
    # The path that actually ran, read off the network's size rather than asserted: below the
    # enumeration bound `fixed_points` walks the state space and never calls z3, and a pin naming
    # z3 over a number z3 did not produce is the defect `solver_pin_for` exists to prevent.
    pin = solver_pin_for(nodes=len(rules))
    return EngineCorroboration(
        quantity=f"{len(rules)}-node fixed-point set",
        engines=(pin.engine, SYMPY_ENGINE),
        distance=0.0 if mine == theirs else 1.0,
        stable=mine == theirs,
        versions=(_reprolith_build(pin), str(sympy.__version__)),
        comparison="exact-match",
    )


__all__ = [
    "EngineCorroboration",
    "corroborate_attractors",
    "corroborate_curve",
    "corroborate_fixed_points",
    "corroborate_objective",
]
