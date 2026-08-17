"""The stochastic (Gillespie SSA) model class simulator (spec: ``stochastic-class``; roadmap parked-item).

Reprolith's fifth model class: discrete-state, continuous-time chemical reaction networks. A single
trajectory is a random sample, so the reproducible result is a *distribution* or a summary
statistic, judged by the population/distributional oracle (:func:`reprolith.judge_distribution`,
:func:`reprolith.judge_scalar`) this class reuses unchanged.

Like the logical class, the simulator is exact and dependency-free — the Gillespie SSA is pure
Python — so this class carries no deferred engine. Its one specialization is *reproducible
sampling*: every run takes an explicit seed, so the same seed and network yield the identical
ensemble and therefore an identical, byte-reproducible verdict, exactly as the deterministic classes
are reproducible under a pinned engine (spec: "Reproducible sampling makes a stochastic reproduction
deterministic").
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace

from .certificate import build_certificate
from .dossier import Dossier, DossierClaim, Equation, Gap, GapKind, Parameter
from .model import Assumption, Certificate, EnginePin, PaperIdentity
from .oracle import Attribution, PercentileBand, Tolerance, judge_scalar


@dataclass(frozen=True)
class Reaction:
    """A mass-action reaction over integer species counts.

    ``reactants`` are ``(species_index, stoichiometry)`` pairs consumed; ``products`` are those
    produced. ``rate`` is the stochastic mass-action rate constant. The propensity follows the
    standard stochastic mass action: ``rate`` times, for each reactant, the falling factorial of its
    count over its stoichiometry divided by that stoichiometry's factorial (so a first-order
    reactant contributes ``n``, a dimerization ``n(n-1)/2``, an empty reactant list ``1``).
    """

    rate: float
    reactants: tuple[tuple[int, int], ...]
    products: tuple[tuple[int, int], ...]

    def __post_init__(self) -> None:
        # A negative or non-finite rate is not a slow reaction, it is a broken one: the total
        # propensity never becomes positive, so every trajectory freezes at its initial state and
        # the SSA reports the initial condition as the reproduced value. That is a *finite* number,
        # so the oracle's non-finite guard cannot see it, and a sign-convention error in an
        # artifact certifies as a perfect reproduction. Refuse it where the reaction is built.
        if not math.isfinite(self.rate) or self.rate < 0.0:
            raise ValueError(
                f"a mass-action rate constant must be finite and non-negative, not {self.rate!r} "
                "(a zero rate is legal — it disables the reaction)"
            )
        seen: set[int] = set()
        for species, _ in self.reactants:
            # Two entries for one species would each contribute their own falling factorial, giving
            # k·n·n where stochastic mass action calls for k·n(n-1)/2, and consuming the species
            # twice per firing — which drives counts negative.
            if species in seen:
                raise ValueError(
                    f"species index {species} appears twice in the reactants; combine repeated "
                    "reactants into a single stoichiometry so the propensity and the consumption "
                    "follow stochastic mass action"
                )
            seen.add(species)

    def propensity(self, state: Sequence[int]) -> float:
        a = self.rate
        for species, stoich in self.reactants:
            count = state[species]
            if count < stoich:
                return 0.0
            term = 1
            for i in range(stoich):
                term *= count - i
            a *= term / math.factorial(stoich)
        return a

    def apply(self, state: list[int]) -> None:
        for species, stoich in self.reactants:
            state[species] -= stoich
        for species, stoich in self.products:
            state[species] += stoich


def _validate_run(initial: Sequence[int], duration: float) -> None:
    """Refuse a run whose request is not a run: the sampler would return the initial state."""
    if not math.isfinite(duration) or duration < 0.0:
        raise ValueError(
            f"a trajectory needs a finite, non-negative duration, not {duration!r}; a run that "
            "cannot advance returns its initial state, which reads as a perfect reproduction"
        )
    negative = [i for i, count in enumerate(initial) if count < 0]
    if negative:
        raise ValueError(f"initial molecule counts must be non-negative; species {negative} are not")


def gillespie(
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    *,
    duration: float,
    rng: random.Random,
    max_events: int | None = None,
) -> list[int]:
    """Run one exact SSA trajectory to ``duration`` and return the final species counts.

    Draws each step from ``rng`` (Gillespie's direct method): the waiting time is exponential in the
    total propensity and the firing reaction is chosen proportional to its propensity. Deterministic
    given ``rng``'s seed — the same seed reproduces the same trajectory (spec: "A pinned seed is part
    of the protocol").

    The event count of an SSA run is ``∫ propensity dt``, which a caller controls through both
    ``duration`` and the network's rate constants — so ``duration`` alone does not bound the work.
    ``max_events`` is an optional safety valve: when set, a trajectory that fires more than that many
    reactions raises ``ValueError`` rather than running unbounded. It defaults to ``None`` (unbounded)
    for trusted callers; untrusted entry points (the MCP linter) pass a finite ceiling.

    A non-finite or negative ``duration``, or a negative initial count, is refused for the reason a
    broken rate is: ``while t < duration`` is false immediately, so the run returns the initial
    state as its result, and a claim reporting the initial condition is then judged a perfect
    reproduction of a simulation that never advanced.
    """
    _validate_run(initial, duration)
    state = list(initial)
    t = 0.0
    events = 0
    while t < duration:
        propensities = [reaction.propensity(state) for reaction in reactions]
        total = math.fsum(propensities)
        if total <= 0.0:
            break  # no reaction can fire — the state is absorbing
        t += -math.log(rng.random()) / total
        if t >= duration:
            break
        if max_events is not None and events >= max_events:
            raise ValueError(
                f"SSA trajectory exceeded {max_events} events before reaching duration "
                f"{duration:.3g}; reduce duration or the network's rates"
            )
        events += 1
        threshold = rng.random() * total
        cumulative = 0.0
        for reaction, propensity in zip(reactions, propensities):
            cumulative += propensity
            if cumulative >= threshold:
                reaction.apply(state)
                break
    return state


def gillespie_at_times(
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    times: Sequence[float],
    *,
    rng: random.Random,
) -> list[list[int]]:
    """Run one SSA trajectory and return the species counts sampled at each time in ``times``.

    The SSA state is piecewise-constant between reaction firings, so each sample time reads the state
    that holds over the interval containing it. ``times`` must be non-decreasing — a stated
    precondition, so it is checked: a sample time before the one preceding it reads a state the
    trajectory has already left behind, silently returning an envelope that never happened.
    """
    ordered = list(times)
    for earlier, later in zip(ordered, ordered[1:]):
        if later < earlier:
            raise ValueError(f"sample times must be non-decreasing; {later} follows {earlier}")
    _validate_run(initial, ordered[-1] if ordered else 0.0)
    state = list(initial)
    t = 0.0
    samples: list[list[int]] = []
    index = 0
    while index < len(ordered):
        propensities = [reaction.propensity(state) for reaction in reactions]
        total = math.fsum(propensities)
        if total <= 0.0:
            while index < len(ordered):  # absorbing: every remaining sample sees this state
                samples.append(list(state))
                index += 1
            break
        t_next = t + -math.log(rng.random()) / total
        while index < len(ordered) and ordered[index] < t_next:
            samples.append(list(state))  # this interval's constant state
            index += 1
        if index >= len(ordered):
            break
        threshold = rng.random() * total
        cumulative = 0.0
        for reaction, propensity in zip(reactions, propensities):
            cumulative += propensity
            if cumulative >= threshold:
                reaction.apply(state)
                break
        t = t_next
    return samples


def _empirical_percentile(values: Sequence[int], percentile: float) -> float:
    """The nearest-rank empirical percentile of ``values`` (percentile in (0, 100))."""
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile / 100.0 * len(ordered)))
    return float(ordered[rank - 1])


def ensemble_percentile_bands(
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    times: Sequence[float],
    *,
    species: int,
    percentiles: Sequence[float],
    trajectories: int,
    seed: int,
) -> tuple[PercentileBand, ...]:
    """Simulate a pinned ensemble and return one species' percentile envelope over ``times``.

    The stochastic counterpart of a population figure: each requested percentile becomes a
    :class:`~reprolith.oracle.PercentileBand` of that species' count across the ensemble at each
    sample time, ready for :func:`reprolith.judge_distribution`. Deterministic in ``seed``.
    """
    if trajectories < 1:
        raise ValueError("need at least one trajectory")
    rng = random.Random(seed)
    # per_time[t] is the list of this species' counts across the ensemble at sample time t.
    per_time: list[list[int]] = [[] for _ in times]
    for _ in range(trajectories):
        trajectory = gillespie_at_times(n_species, reactions, initial, times, rng=rng)
        for i, sampled in enumerate(trajectory):
            per_time[i].append(sampled[species])
    return tuple(
        PercentileBand(
            percentile,
            tuple(_empirical_percentile(per_time[i], percentile) for i in range(len(times))),
        )
        for percentile in percentiles
    )


def ensemble_final_counts(
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    *,
    duration: float,
    trajectories: int,
    seed: int,
    max_events: int | None = None,
) -> list[list[int]]:
    """Run ``trajectories`` independent SSA runs from one pinned ``seed`` and return their final counts.

    A single ``random.Random(seed)`` drives every trajectory in sequence, so the whole ensemble is a
    deterministic function of ``seed`` — the reproducible-sampling contract that lets a stochastic
    reproduction be certified byte-for-byte. ``max_events`` is forwarded to each trajectory as a
    per-run safety valve (see :func:`gillespie`); ``None`` leaves them unbounded.
    """
    if trajectories < 1:
        raise ValueError("need at least one trajectory")
    rng = random.Random(seed)
    return [
        gillespie(n_species, reactions, initial, duration=duration, rng=rng, max_events=max_events)
        for _ in range(trajectories)
    ]


def species_mean_variance(ensemble: Sequence[Sequence[int]], species: int) -> tuple[float, float]:
    """The sample mean and (population) variance of one species' final count across the ensemble."""
    if not ensemble:
        raise ValueError("need at least one trajectory")
    values = [run[species] for run in ensemble]
    n = len(values)
    mean = math.fsum(values) / n
    variance = math.fsum((v - mean) ** 2 for v in values) / n
    return mean, variance


@dataclass(frozen=True)
class StochasticClaim:
    """A published stochastic summary-statistic claim: a reported mean species count to reproduce.

    ``species`` indexes the network species; ``reported_mean`` is the paper's value. The sampling
    protocol — ``duration``, number of ``trajectories``, and the ``seed`` — is recorded so the
    reproduction is byte-reproducible (spec: "A pinned seed is part of the protocol"). ``shortfall``
    supplies the root cause a non-pass verdict requires.
    """

    claim_id: str
    quantity: str
    species: int
    reported_mean: float
    source_location: str
    duration: float
    trajectories: int
    seed: int
    tolerance: Tolerance | None = None
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)


def certify_stochastic(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    claims: Iterable[StochasticClaim],
    assumptions: Iterable[Assumption] = (),
) -> Certificate:
    """Run each claim's pinned ensemble, judge its mean, and assemble the certificate.

    The stochastic class front-end (the counterpart of ``certify_logical`` / ``certify_curves``):
    each claim's mean species count is reproduced from a seeded SSA ensemble and judged by the
    shared scalar oracle, then the certificate is built by the same rule and scope flag as every
    other class. Verdicts are assumption-qualified by default because a stochastic reproduction
    depends on the sampling (seed and trajectory count). Needs no engine extra — the SSA is pure.

    Each assessment carries the sampling protocol it rests on, because a sampled number nobody can
    re-run is not evidence: the seed and trajectory count are what make this class's verdicts
    byte-reproducible (spec: "A pinned seed is part of the protocol"), and recording them is also
    what makes a seed that merely happened to agree visible to a reader.
    """
    assessments = []
    for claim in claims:
        ensemble = ensemble_final_counts(
            n_species, reactions, initial,
            duration=claim.duration, trajectories=claim.trajectories, seed=claim.seed,
        )
        mean, _ = species_mean_variance(ensemble, claim.species)
        assessment = judge_scalar(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.reported_mean,
            predicted=mean,
            tolerance=claim.tolerance,
            attribution=claim.shortfall,
            assumption_qualified=claim.assumption_qualified,
        )
        assessments.append(
            replace(
                assessment,
                protocol=(
                    f"SSA ensemble: {claim.trajectories} trajectories to t={claim.duration:g}, "
                    f"seed {claim.seed}"
                ),
            )
        )
    return build_certificate(
        paper=paper, engine_pin=engine_pin,
        assessments=assessments, assumptions=tuple(assumptions),
    )


def time_to_extinction(
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    *,
    species: int,
    rng: random.Random,
    max_time: float = 1e9,
) -> float:
    """The first time ``species`` reaches zero along one SSA trajectory (its extinction time).

    Runs the direct method until the species count hits zero (or ``max_time`` / an absorbing state
    with no further reactions). The extinction time of a small population is a first-passage
    observable central to population dynamics — extinction of small populations, loss of a
    drug-resistant clone. Deterministic in ``rng``.
    """
    state = list(initial)
    t = 0.0
    while state[species] > 0 and t < max_time:
        propensities = [reaction.propensity(state) for reaction in reactions]
        total = math.fsum(propensities)
        if total <= 0.0:
            break
        t += -math.log(rng.random()) / total
        threshold = rng.random() * total
        cumulative = 0.0
        for reaction, propensity in zip(reactions, propensities):
            cumulative += propensity
            if cumulative >= threshold:
                reaction.apply(state)
                break
    return t


def fano_factor(ensemble: Sequence[Sequence[int]], species: int) -> float:
    """The Fano factor (variance / mean) of a species across the ensemble.

    The signature of the noise regime: 1 for Poisson (constitutive) statistics, greater than 1 for
    super-Poissonian/bursty expression, less than 1 for sub-Poissonian. A fundamental readout in
    single-cell and gene-expression biology.
    """
    mean, variance = species_mean_variance(ensemble, species)
    if mean == 0.0:
        raise ValueError("Fano factor is undefined for a zero mean")
    return variance / mean


def coefficient_of_variation(ensemble: Sequence[Sequence[int]], species: int) -> float:
    """The coefficient of variation (standard deviation / mean) of a species across the ensemble.

    The relative noise level; for Poisson statistics it scales as ``1/√mean`` — the fundamental law
    that smaller molecule populations are proportionally noisier.
    """
    mean, variance = species_mean_variance(ensemble, species)
    if mean == 0.0:
        raise ValueError("coefficient of variation is undefined for a zero mean")
    return math.sqrt(variance) / mean


def validate_stochastic(dossier: Dossier) -> list[str]:
    """Structural problems that make a stochastic dossier ill-formed; empty when well-formed.

    On top of the shared checks: an unstated sampling protocol (seed and trajectory count) must be a
    load-bearing gap, because it determines the ensemble and therefore the reproduced statistic
    (spec: stochastic-class — "A pinned seed is part of the protocol").
    """
    problems = dossier.validate()
    for gap in dossier.gaps:
        if gap.kind is GapKind.SAMPLING and not gap.load_bearing:
            problems.append("an unstated sampling protocol must be recorded as a load-bearing gap")
    return problems


def stochastic_dossier(
    entry: str,
    *,
    species: Mapping[str, int],
    reactions: Sequence[Equation],
    rates: Sequence[Parameter],
    source_location: str,
    sampling_stated: bool,
    claims: Sequence[DossierClaim] = (),
) -> Dossier:
    """Assemble a well-formed stochastic dossier, or raise if it is ill-formed.

    Records the ``species`` with their initial molecule counts (as initial conditions), each
    reaction's stoichiometry (as an equation) and its ``rates`` (mass-action rate constants), and
    the reported statistic ``claims``. When ``sampling_stated`` is false the seed/trajectory-count
    protocol is recorded as a load-bearing :class:`~reprolith.dossier.Gap`. Validated by
    :func:`validate_stochastic`.
    """
    initial_conditions = tuple(
        Parameter(name=name, value=float(count), unit="molecules", source_location=source_location)
        for name, count in sorted(species.items())
    )
    gaps: tuple[Gap, ...] = ()
    if not sampling_stated:
        gaps = (Gap(
            element="sampling protocol",
            kind=GapKind.SAMPLING,
            detail="the paper does not state the random seed and number of trajectories",
            load_bearing=True,
        ),)
    dossier = Dossier(
        entry=entry,
        state_variables=tuple(sorted(species)),
        equations=tuple(reactions),
        parameters=tuple(rates),
        initial_conditions=initial_conditions,
        claims=tuple(claims),
        gaps=gaps,
    )
    problems = validate_stochastic(dossier)
    if problems:
        raise ValueError("ill-formed stochastic dossier: " + "; ".join(problems))
    return dossier


__all__ = [
    "Reaction",
    "StochasticClaim",
    "certify_stochastic",
    "coefficient_of_variation",
    "fano_factor",
    "stochastic_dossier",
    "validate_stochastic",
    "ensemble_final_counts",
    "ensemble_percentile_bands",
    "gillespie",
    "gillespie_at_times",
    "species_mean_variance",
    "time_to_extinction",
]
