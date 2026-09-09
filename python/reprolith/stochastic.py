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
from .enums import Verdict
from .model import Assumption, Certificate, ClaimAssessment, EnginePin, PaperIdentity
from .oracle import (
    Attribution,
    ComparisonMethod,
    PercentileBand,
    ReferenceKind,
    SpreadStatistic,
    Tolerance,
    default_tolerance,
    judge_scalar,
    not_evaluable,
    relative_error,
    resolving_sample_clause,
    spread_standard_error,
    spread_statistic,
    undetermined_shortfall,
)
from .pins import algorithm_revision


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

    An ensemble too small to resolve the bands it is asked for is refused, the way the scalar path
    refuses one too small to resolve a mean (:data:`_SPREAD_IS_EVIDENCE`). Two ways it can be too
    small, both measured on a provably correct model: below ~30 trajectories the envelope is
    dominated by sampling noise, and a model whose mean is exactly right published `failed` on 96
    of 100 seeds at three trajectories; and a percentile needs about ``100/min(p, 100-p)``
    trajectories before it is a percentile at all rather than the observed min or max wearing a
    label — at one trajectory, P1, P50 and P99 are the same number reported three times as an
    "envelope". Neither can be caught downstream: :func:`judge_distribution` receives bare bands
    and never learns the ensemble size.
    """
    if trajectories < 1:
        raise ValueError("need at least one trajectory")
    # The request itself is checked before the ensemble size, so a malformed run is refused for
    # the reason it is malformed rather than for being too small to resolve.
    ordered = sorted(times)
    if list(times) != ordered:
        raise ValueError("times must be non-decreasing")
    _validate_run(initial, ordered[-1] if ordered else 0.0)
    if trajectories < _SPREAD_IS_EVIDENCE:
        raise ValueError(
            f"{trajectories} trajectories cannot resolve a percentile envelope: below "
            f"{_SPREAD_IS_EVIDENCE} the spread is the sampling, not the model, and a correct "
            "model is published as a failure"
        )
    for percentile in percentiles:
        tail = min(percentile, 100.0 - percentile)
        # `<=`, not `<`: `_empirical_percentile` is nearest-rank, so `n·tail == 100` is exactly
        # rank 1 — the observed minimum. P2.5 at n=40 (an ordinary 95% envelope) and P1 at n=100
        # both landed on that boundary and returned the elementwise minimum wearing a band label.
        if tail > 0.0 and trajectories * tail <= 100.0:
            raise ValueError(
                f"the P{percentile:g} band needs about {math.ceil(100.0 / tail)} trajectories to "
                f"be a percentile rather than the observed extreme; {trajectories} were run"
            )
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


@dataclass(frozen=True)
class ExtinctionTimeClaim:
    """A published **mean time to extinction**: how long a small population survives.

    The class's third reproduction target, and the one that is a *first-passage* observable rather
    than a state at a fixed time. It is what population-dynamics and resistance papers report — how
    long a small population, or a drug-resistant clone, persists before its last individual is
    gone — and it is a number a paper prints, so it is reachable without any figure.

    The protocol is the claim's, exactly as it is for a mean count: ``trajectories`` and ``seed``
    make the run byte-reproducible, and ``max_time`` bounds each trajectory. That bound is part of
    the claim rather than a hidden default because it decides what the number *means*: a run that
    reaches it has observed no extinction, and :func:`time_to_extinction` returns infinity for it
    rather than the cap.
    """

    claim_id: str
    quantity: str
    species: int
    reported_mean: float
    source_location: str
    trajectories: int
    seed: int
    #: The hard cap on each trajectory. A run that reaches it observed no extinction, and the claim
    #: abstains rather than averaging over the ones that finished — see :func:`_judge_extinction`.
    max_time: float
    tolerance: Tolerance | None = None
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)

    def __post_init__(self) -> None:
        if self.trajectories < 2:
            raise ValueError(
                f"claim {self.claim_id!r} asks for {self.trajectories} trajectories: a mean "
                "first-passage time needs an ensemble, and its standard error needs at least two"
            )
        if self.max_time <= 0.0:
            raise ValueError(
                f"claim {self.claim_id!r} caps each run at {self.max_time!r}: a run that cannot "
                "advance observes no extinction"
            )


#: The sampling assumption's basis, shared by every claim this class qualifies. Identical wording
#: on purpose: a verification-queue item is keyed by its question, so one sampling limitation asked
#: by several claims is one item with several dependents rather than one question each. The
#: per-claim number lives on the protocol line, where the rest of that run's facts already are —
#: the spatial class learned that the expensive way.
#:
#: It says "estimate" and not "mean" because this class stopped judging only means: a Fano factor
#: and a coefficient of variation rest on the same sampling and the same pinned seed, and a basis
#: naming a mean would have described a quantity two of its dependents are not about.
_SAMPLING_BASIS = (
    "a finite ensemble's estimate differs from the model's true value by sampling noise of a size "
    "the trajectory count sets, so the verdict moves with the count and the seed; both are pinned "
    "here to make it byte-reproducible. How far it moves is measured rather than left as a caveat: "
    "this claim's protocol line reports that estimate's standard error as a share of the reported "
    "value, against the threshold it is judged at"
)


#: How much of the distance between a claim's answer and its nearest verdict line the sampling
#: error may account for before the ensemble is reported as able to decide the verdict. The same
#: tenth the spatial class holds a finite grid to for an unbounded domain
#: (:data:`reprolith.spatial.UNBOUNDED_WALL_BUDGET`), and for the same reason — a bound that is a
#: tenth of what a verdict turns on cannot be what turned it. Advisory here: nothing gates on it,
#: because unlike a wall, an ensemble's error is not something a curator can measure away without
#: re-running the claim. What it buys is a number in place of "a larger ensemble".
SAMPLING_MARGIN_BUDGET = 0.1


def ensemble_to_settle(
    *, relative_error: float, relative_sem: float, trajectories: int, tolerance: Tolerance
) -> tuple[int, float] | None:
    """How large an ensemble would put this claim's sampling noise out of the verdict's way.

    The queue's alternative to a sampled ensemble reads "a larger ensemble", which is true of every
    ensemble ever drawn and tells a reader nothing. This answers *how much* larger: the standard
    error falls as 1/√n, so reaching a tenth of the margin between this claim's answer and its
    nearest verdict line takes ``n × (sem / (0.1 × margin))²`` trajectories.

    Returns ``(trajectories, margin)``, or ``None`` when the claim already sits far enough from
    both lines — there is nothing to buy — or when the margin is zero, where no finite ensemble
    settles a claim landing exactly on its threshold.
    """
    margin = min(
        abs(relative_error - tolerance.reproduced_within),
        abs(relative_error - tolerance.partial_within),
    )
    if margin <= 0.0:
        return None
    target = SAMPLING_MARGIN_BUDGET * margin
    if relative_sem <= target:
        return None
    return math.ceil(trajectories * (relative_sem / target) ** 2), margin


def _settling_clause(
    *, reported: float, observed: float, relative_sem: float, trajectories: int,
    tolerance: Tolerance,
) -> str:
    """The "and this is what would settle it" half of a sampling-cost clause, or ``""``.

    Written once for the three kinds of ensemble claim this class judges. The first version of this
    reached only the mean, which is three of the five queue items it exists to answer — and a rule
    that covers every case it was written for but one is a shape this repository has caught in
    itself before.
    """
    settle = ensemble_to_settle(
        relative_error=relative_error(reported, observed),
        relative_sem=relative_sem,
        trajectories=trajectories,
        tolerance=tolerance,
    )
    if settle is None:
        return ""
    needed, margin = settle
    return (
        f"; this answer sits {margin:.2%} from the nearest verdict line, so ~{needed:,} "
        f"trajectories — {needed / trajectories:.0f}x this ensemble — would put the sampling "
        "error a tenth of the way to it"
    )


def _sampling_cost(
    claim: StochasticClaim,
    variance: float,
    trajectories: int,
    observed_mean: float | None = None,
) -> str:
    """What this ensemble's size buys the claim, as a clause for the protocol line.

    The assumption behind every stochastic certificate says the verdict "moves with the count and
    the seed" and could not say by how much. It can: the ensemble's own standard error is the size
    of that movement, it was already computed to decide whether to abstain, and it was reported
    only when the answer was no. On the protocol line rather than in the assumption's basis — the
    basis states one fact about this engine, and a per-claim number there splits one question into
    several (the spatial class learned that the expensive way).
    """
    measured = ensemble_headroom(
        reported_mean=claim.reported_mean,
        variance=variance,
        trajectories=trajectories,
        tolerance=claim.tolerance,
    )
    if measured is None:
        return ""
    relative_sem, threshold = measured
    clause = (
        f" (sampling noise: the mean's standard error is {relative_sem:.2%} of the reported value, "
        f"against a {threshold:.0%} pass threshold"
    )
    if observed_mean is not None:
        clause += _settling_clause(
            reported=claim.reported_mean, observed=observed_mean, relative_sem=relative_sem,
            trajectories=trajectories,
            tolerance=claim.tolerance or default_tolerance(
                ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
            ),
        )
    return clause + ")"


def _protocol(claim: StochasticClaim) -> str:
    """The sampling a stochastic assessment rests on, in the form the certificate records.

    The species is named because it is the only per-claim degree of freedom that moves the number:
    the network, the initial state and the species count are all certificate-level, so two claims
    reading different species had byte-identical protocols while disagreeing about the answer. Every
    other class with a read to choose records it — the ODE classes write `read=[X] cmax`, FBA writes
    `maximize: <reaction>` — and this was the one that did not.
    """
    return (
        f"SSA ensemble: {claim.trajectories} trajectories to t={claim.duration:g}, "
        f"seed {claim.seed}, read=species[{claim.species}]"
    )


def _sampling_cannot_resolve(
    claim: StochasticClaim, variance: float, trajectories: int, observed_mean: float
) -> ClaimAssessment | None:
    """Abstain when the ensemble's own noise is too large to decide the claim, else ``None``.

    The tolerance is a fixed threshold; the noise around the mean is not — the caller sets it with
    the trajectory count. At ten trajectories a *provably correct* immigration-death model fails
    its 5% claim on 25 of 40 seeds, so the class publishes ``not-reproduced`` against an author
    whose model is exactly right. The root cause recorded is honest (finite-ensemble sampling), but
    the headline is a false accusation, and no reader reads past the headline.

    So when the standard error of the mean is more than half the pass threshold — the regime where
    a correct model routinely misses and a wrong one routinely passes — the honest verdict is that
    this ensemble cannot resolve this claim, which is an abstention, not a failure. Enlarging the
    ensemble is the fix, and the reason says so.
    """
    reason = unresolvable_ensemble_reason(
        reported_mean=claim.reported_mean, variance=variance, trajectories=trajectories,
        observed_mean=observed_mean, tolerance=claim.tolerance,
    )
    if reason is None:
        return None
    return not_evaluable(
        claim_id=claim.claim_id,
        quantity=claim.quantity,
        source_location=claim.source_location,
        reason=reason,
        reference_kind=ReferenceKind.NUMERIC,
    )


#: Below this many trajectories, an ensemble that produced no spread at all is not evidence that
#: the process is deterministic. Measured on the immigration-death model over 500 seeds, an exactly
#: zero sample variance appears in 14.6% of 2-trajectory ensembles, 2.8% at three, 0.8% at four,
#: and 0.0% at ten; the bar sits well above the largest size where it was seen.
_SPREAD_IS_EVIDENCE = 30


#: How many standard errors clear of the pass band an observed mean must sit before sampling noise
#: is ruled out as the explanation. Measured on the immigration-death model (true mean 10, 200
#: seeds per size): at ten trajectories a *correct* model would be published as a false
#: `not-reproduced` on 9 of 200 seeds at two standard errors and 2 of 200 at three, with four
#: buying no further improvement — so three is where the curve flattens. At forty trajectories and
#: above it is 0 of 200. Every wrong model measured (+20%, threefold, tenfold) re-opens at all
#: three values, so the choice costs nothing on the side it exists to serve.
_DECISIVELY_OUTSIDE = 3.0


def unresolvable_ensemble_reason(
    *,
    reported_mean: float,
    variance: float,
    trajectories: int,
    observed_mean: float | None = None,
    tolerance: Tolerance | None = None,
    standard_error: float | None = None,
    quantity_noun: str = "reported mean",
) -> str | None:
    """Why this ensemble cannot decide this claim, or ``None`` when it can.

    The rule both stochastic paths share — the certificate path above, and the inline linter, which
    judges the same kind of number for an agent about to gate a workflow on it. Whether an ensemble
    can resolve a claim is a property of the ensemble and the threshold, not of which surface asked,
    so the two must not be able to disagree: at ten trajectories a provably correct
    immigration-death model misses its 5% claim on most seeds, and a linter answering ``failed``
    there is a false accusation an agent acts on immediately.
    """
    # The zero-spread guard runs first, because a reported mean of zero is the value this check
    # should be strictest at, not the one that switches it off. An extinction or no-expression
    # claim took the early return below and skipped resolvability entirely, so a one-trajectory
    # ensemble that happened to land on 0 published `reproduced` at "relative error 0.0000":
    # measured on immigration-death with a true mean of 1.0, that is 87 of 200 seeds at one
    # trajectory and 27 at two, against 0 once the guard is allowed to see the case.
    if variance <= 0.0 and trajectories < _SPREAD_IS_EVIDENCE:
        # A zero spread means "this ensemble resolves the claim" only once the ensemble is large
        # enough for zero to be a measurement rather than an accident. One trajectory has a
        # variance of 0 by construction; two draws of a genuinely stochastic model land on the
        # same value 14.6% of the time (500 seeds, immigration-death), 2.8% at three, and 0% by
        # ten. Below the bar the standard-error guard was skipped exactly where the sampling noise
        # is largest, and an exactly-correct model published `reproduced` or `failed` by lottery.
        return (
            f"this ensemble cannot resolve the claim: {trajectories} trajector"
            f"{'y' if trajectories == 1 else 'ies'} produced no spread at all, which at that size "
            "is as likely an accident as a measurement, so it cannot tell a reproduction from "
            f"noise; at {_SPREAD_IS_EVIDENCE} trajectories or more a zero spread is a measurement "
            "and this check reads it as one"
        )
    if reported_mean == 0.0:
        return None
    if variance <= 0.0:
        return None
    tol = tolerance or default_tolerance(
        ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
    )
    # A mean's error bar is sqrt(variance/n); a ratio of moments — a Fano factor, a coefficient of
    # variation — has a different one, measured by resampling rather than by that formula. The
    # caller supplies it in that case, so the *rule* (the half-threshold bar, the zero-spread bar,
    # the decisively-outside escape) stays one implementation for every quantity this class judges.
    sem = math.sqrt(variance / trajectories) if standard_error is None else standard_error
    relative_sem = abs(sem / reported_mean)
    if relative_sem <= tol.reproduced_within / 2.0:
        return None
    # The rule above compares the *reconstruction's* noise to the *paper's* number, and for a
    # counting process the variance grows with the mean — so the further a reconstruction
    # over-predicts, the noisier it is and the more certainly it was ruled unresolvable. A model
    # over-predicting threefold sat 71 standard errors outside the pass band and was published as
    # `blocked`, whose published meaning is "insufficient information", under a reason that was
    # arithmetically false. It was one-sided too: a hundredfold *under*-prediction was judged,
    # because under-predicting shrinks the variance.
    #
    # So: however noisy the ensemble, if the observed mean is clear of the pass band by more than
    # `_DECISIVELY_OUTSIDE` standard errors, sampling noise cannot be what put it there, and the
    # honest verdict is the miss, not an abstention. This can only turn an abstention into a
    # judgement, never the reverse, so no verdict that stands today can flip to blocked.
    if observed_mean is not None:
        band = tol.reproduced_within * abs(reported_mean)
        if abs(observed_mean - reported_mean) > band + _DECISIVELY_OUTSIDE * sem:
            return None
    return (
        f"this ensemble cannot resolve the claim: its standard error is "
        f"{relative_sem:.1%} of the {quantity_noun}, against a "
        f"{tol.reproduced_within:.0%} pass threshold; "
        f"{trajectories} trajectories is too few to tell a reproduction from sampling noise"
        + resolving_sample_clause(
            relative_error_bar=relative_sem,
            size=trajectories,
            pass_threshold=tol.reproduced_within,
            noun="trajectories",
        )
    )


def ensemble_headroom(
    *, reported_mean: float, variance: float, trajectories: int, tolerance: Tolerance | None = None
) -> tuple[float, float] | None:
    """This ensemble's sampling noise and the threshold it is judged against, or ``None``.

    The same standard error :func:`unresolvable_ensemble_reason` abstains on — reported for the
    claims that *did* resolve, which is where it was invisible. That check speaks only when the
    noise is too large; a claim it passes says nothing about whether it passed at half the line or
    at a fiftieth of it, and those are very different certificates. Both published the same
    unquantified sentence: "the verdict moves with the count and the seed".

    Returns ``(relative standard error, pass threshold)``, both as fractions of the reported mean.
    ``None`` where the quantity is undefined — a zero reported mean, or an ensemble with no spread
    — which are exactly the cases the abstention rule handles separately.
    """
    if reported_mean == 0.0 or variance <= 0.0 or trajectories <= 0:
        return None
    tol = tolerance or default_tolerance(
        ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
    )
    sem = math.sqrt(variance / trajectories)
    return abs(sem / reported_mean), tol.reproduced_within


def solver_pin() -> EnginePin:
    """The :class:`~reprolith.model.EnginePin` for this module's SSA, at its current revision.

    The solver is this package, so the pin's version is the package's — and that version has never
    moved. Freshness is decided by comparing a certificate's pin to the current one, so the SSA
    could be fixed without a single certificate it invalidates being flagged for re-verification.
    The algorithm field therefore names the revision of the code that computed the ensemble (see
    :func:`reprolith.pins.algorithm_revision`), which moves whenever this module or the oracle it
    judges through does.
    """
    from . import __version__  # local: the package imports this module while initializing

    revision = algorithm_revision("stochastic", "oracle", "certificate")
    return EnginePin(
        engine="reprolith-ssa",
        version=__version__,
        algorithm=f"gillespie-direct-method (rev {revision})",
    )


def _judge_extinction(
    claim: ExtinctionTimeClaim,
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
) -> tuple[ClaimAssessment, float, float | None]:
    """Run the claim's ensemble of first passages and judge the mean, or say why it cannot be.

    Returns the assessment, the ensemble's variance, and the mean it measured — the last so the
    caller's cost clause can say how far this answer sits from its verdict line. ``None`` where no
    mean was formed, which is every abstention here.

    Returns the assessment and the ensemble's variance, which the protocol line reports as the
    sampling cost exactly as it does for a mean count.

    Two ways this abstains rather than publishing a number:

    ``a run observed no extinction``
        :func:`time_to_extinction` returns infinity for a trajectory that hit ``max_time`` or an
        absorbing state, and a mean over the finished ones alone is the mean of a *conditioned*
        sample — systematically short, and short by an amount nobody can bound from the sample
        itself. Averaging the finite ones is how a cap silently becomes the answer, which is the
        defect the infinity was introduced to prevent; this refuses to average past it and says how
        many runs did not finish.
    ``the ensemble cannot resolve the claim``
        the same rule the mean count is held to: when the standard error is more than half the pass
        threshold, a correct model routinely misses and a wrong one routinely passes, so the honest
        verdict is that this ensemble cannot decide it.
    """
    rng = random.Random(claim.seed)
    times = [
        time_to_extinction(
            n_species, reactions, initial,
            species=claim.species, rng=rng, max_time=claim.max_time,
        )
        for _ in range(claim.trajectories)
    ]
    censored = sum(1 for value in times if not math.isfinite(value))
    if censored:
        return (
            not_evaluable(
                claim_id=claim.claim_id,
                quantity=claim.quantity,
                source_location=claim.source_location,
                reason=(
                    f"{censored} of {claim.trajectories} trajectories observed no extinction — "
                    f"they reached the {claim.max_time!r} cap, or a state from which the species "
                    "can never reach zero, and the two are the same to a first-passage reading. "
                    "A mean over the runs that finished is the mean of a conditioned sample and "
                    "is short by an amount the sample cannot bound — run longer, or check that "
                    "this species can go extinct in this network at all"
                    + (
                        ". Every trajectory is in that state, which points at the network rather "
                        "than at the cap"
                        if censored == claim.trajectories else ""
                    )
                ),
                reference_kind=ReferenceKind.NUMERIC,
            ),
            0.0,
            None,
        )
    mean = sum(times) / len(times)
    variance = sum((value - mean) ** 2 for value in times) / (len(times) - 1)
    reason = unresolvable_ensemble_reason(
        reported_mean=claim.reported_mean, variance=variance, trajectories=len(times),
        observed_mean=mean, tolerance=claim.tolerance,
    )
    if reason is not None:
        return (
            not_evaluable(
                claim_id=claim.claim_id, quantity=claim.quantity,
                source_location=claim.source_location, reason=reason,
                reference_kind=ReferenceKind.NUMERIC,
            ),
            variance,
            None,
        )
    return (
        judge_scalar(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.reported_mean,
            predicted=mean,
            tolerance=claim.tolerance,
            attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
            assumption_qualified=claim.assumption_qualified,
        ),
        variance,
        mean,
    )


def certify_stochastic(
    *,
    paper: PaperIdentity,
    engine_pin: EnginePin,
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
    claims: Iterable[StochasticClaim] = (),
    extinctions: Iterable[ExtinctionTimeClaim] = (),
    noises: Iterable[NoiseClaim] = (),
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

    A qualified claim's qualification is also written down as an
    :class:`~reprolith.model.Assumption` naming that sampling. The flag on its own says "this
    reproduction rests on an assumption Reprolith supplied" while listing none, which reads to
    anyone outside this class like a missing record rather than the class's real caveat: the
    ensemble is Reprolith's choice, and the verdict moves with it.
    """
    claims = tuple(claims)
    judged: list[StochasticClaim] = []
    assessments = []
    for claim in claims:
        # A run that does not advance is not evidence about the model: the ensemble comes back as
        # the initial state, and a claim stated at that state judges as `reproduced` at relative
        # error 0.0000. Both time-advancing siblings refuse it at their certifying front end —
        # spatial for `steps < 1`, the ODE engine for a non-positive duration — and the MCP
        # boundary already refuses it here. The sampler itself keeps allowing a zero-duration
        # request, which is a well-defined way to ask for the initial state; what is refused is
        # certifying a claim against one.
        if claim.duration <= 0.0:
            raise ValueError(
                f"claim {claim.claim_id!r} asks for a run of {claim.duration!r} time units: a "
                "stochastic claim must advance the ensemble to be evidence about the model"
            )
        ensemble = ensemble_final_counts(
            n_species, reactions, initial,
            duration=claim.duration, trajectories=claim.trajectories, seed=claim.seed,
        )
        mean, variance = species_mean_variance(ensemble, claim.species)
        unresolvable = _sampling_cannot_resolve(claim, variance, len(ensemble), mean)
        if unresolvable is not None:
            assessments.append(replace(unresolvable, protocol=_protocol(claim)))
            continue
        assessment = judge_scalar(
            claim_id=claim.claim_id,
            quantity=claim.quantity,
            source_location=claim.source_location,
            reported=claim.reported_mean,
            predicted=mean,
            tolerance=claim.tolerance,
            # A failed verdict must carry a root cause, and a claim that supplies none used to
            # raise instead of certifying — so a seed that happened to miss crashed the run rather
            # than producing the honest not-reproduced certificate it had earned. The cause used to
            # default to FINITE_ENSEMBLE_SAMPLING, but nothing reaches this line until the guard
            # above has established that the ensemble's noise is *too small* to explain a miss: the
            # certificate was filing a 107% discrepancy under a 2.2% noise source, which is exactly
            # the "nearest wrong cause" that `uncategorized` exists to prevent. This class now
            # defaults the way every other class front-end does; a caller who has actually
            # diagnosed finite-ensemble sampling still supplies it.
            attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
            assumption_qualified=claim.assumption_qualified,
        )
        assessments.append(
            replace(
                assessment,
                # The judged claims are the ones this was invisible on: the abstention rule reports
                # the ensemble's noise only when it is too large to decide anything.
                protocol=_protocol(claim) + _sampling_cost(
                    claim, variance, len(ensemble), observed_mean=mean,
                ),
            )
        )
        judged.append(claim)
    # Only the claims a verdict was drawn from: an abstention concluded nothing, so an assumption
    # saying its mean rests on this ensemble would describe a judgment that was never made — and,
    # being load-bearing, would downgrade the certificate on behalf of a claim nobody judged.
    sampling = tuple(
        Assumption(
            id=f"ssa-sampling-{claim.claim_id}",
            description=(
                "the mean judged here is the average of an ensemble Reprolith sampled, not a "
                "number the paper's own run produced"
            ),
            chosen=_protocol(claim),
            basis=_SAMPLING_BASIS,
            load_bearing=True,
            alternatives=("a different seed", "a larger ensemble"),
            # The ensemble is Reprolith's sampling choice, not anything the paper
            # left out, so nothing the author writes clears it.
            author_can_close=False,
        )
        for claim in judged
        if claim.assumption_qualified
    )
    # The first-passage claims, judged by the same rules and carrying the same assumption: the
    # ensemble is Reprolith's, and its cost is measured on the protocol line rather than asserted.
    extinction_claims = tuple(extinctions)
    extinction_sampling: list[Assumption] = []
    for extinction in extinction_claims:
        assessment, variance, observed = _judge_extinction(
            extinction, n_species, reactions, initial
        )
        # The cost clause goes on a *judged* assessment only, as it does for a mean count. On an
        # abstention the reason already carries the ensemble's noise, and printing it again from a
        # second formatter gave one number two roundings — 20.1% in the reason and 20.08% in the
        # protocol — which is this repository's "two accounts of one computation" in miniature.
        protocol = _extinction_protocol(extinction)
        if assessment.verdict is not Verdict.NOT_EVALUABLE:
            protocol += _extinction_cost(extinction, variance, observed_mean=observed)
        assessments.append(replace(assessment, protocol=protocol))
        if assessment.assumption_qualified:
            extinction_sampling.append(
                Assumption(
                    id=f"ssa-sampling-{extinction.claim_id}",
                    description=(
                        "the mean extinction time judged here is the average of an ensemble "
                        "Reprolith sampled, not a number the paper's own run produced"
                    ),
                    chosen=_extinction_protocol(extinction),
                    basis=_SAMPLING_BASIS,
                    load_bearing=True,
                    alternatives=("a different seed", "a larger ensemble"),
                    author_can_close=False,
                )
            )
    # The **noise** claims, judged by the same rules again: the ensemble is Reprolith's, its cost
    # is measured rather than asserted, and what is measured is the statistic's own error bar
    # rather than a mean's — see :func:`noise_standard_error`.
    noise_sampling: list[Assumption] = []
    for noise in tuple(noises):
        assessment = _judge_noise(noise, n_species, reactions, initial)
        assessments.append(assessment)
        if assessment.assumption_qualified:
            noise_sampling.append(
                Assumption(
                    id=f"ssa-sampling-{noise.claim_id}",
                    description=(
                        # Not "the fano-factor judged here": the queue keys an item by its
                        # question, and a description naming the statistic asks the same question
                        # once per statistic. Both rest on the same ensemble and the same choice,
                        # so this is one item with two dependents — which is what the per-claim
                        # `chosen` line below is for.
                        "the noise statistic judged here is computed from an ensemble Reprolith "
                        "sampled, not a number the paper's own run produced"
                    ),
                    # The ensemble, without the read. What Reprolith chose is the sampling; which
                    # statistic is read off it is the claim's question, not this engine's estimate
                    # — and putting it here made the same limitation, asked twice of one ensemble,
                    # two verification-queue items instead of one item with two dependents.
                    chosen=(
                        f"SSA ensemble: {noise.trajectories} trajectories to "
                        f"t={noise.duration:g}, seed {noise.seed}"
                    ),
                    basis=_SAMPLING_BASIS,
                    load_bearing=True,
                    alternatives=("a different seed", "a larger ensemble"),
                    author_can_close=False,
                )
            )
    if not assessments:
        raise ValueError(
            "a stochastic certificate needs at least one claim: certifying a paper this class "
            "judged nothing of would publish a verdict about no evidence"
        )
    return build_certificate(
        paper=paper, engine_pin=engine_pin,
        assessments=assessments,
        assumptions=(*assumptions, *sampling, *extinction_sampling, *noise_sampling),
    )


def _extinction_protocol(claim: ExtinctionTimeClaim) -> str:
    """The run behind a first-passage verdict, in the form a reader can re-run."""
    return (
        f"SSA first passage: {claim.trajectories} trajectories, seed {claim.seed}, "
        f"species[{claim.species}] to zero, each capped at t={claim.max_time!r}"
    )


def _extinction_cost(
    claim: ExtinctionTimeClaim, variance: float, observed_mean: float | None = None
) -> str:
    """What this ensemble's size buys the first-passage claim, measured as it is for a mean."""
    measured = ensemble_headroom(
        reported_mean=claim.reported_mean,
        variance=variance,
        trajectories=claim.trajectories,
        tolerance=claim.tolerance,
    )
    if measured is None:
        return ""
    relative_sem, threshold = measured
    clause = (
        f" (sampling noise: the mean's standard error is {relative_sem:.2%} of the reported "
        f"value, against a {threshold:.0%} pass threshold"
    )
    if observed_mean is not None:
        clause += _settling_clause(
            reported=claim.reported_mean, observed=observed_mean, relative_sem=relative_sem,
            trajectories=claim.trajectories,
            tolerance=claim.tolerance or default_tolerance(
                ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
            ),
        )
    return clause + ")"


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

    Runs the direct method until the species count hits zero. The extinction time of a small
    population is a first-passage observable central to population dynamics — extinction of small
    populations, loss of a drug-resistant clone. Deterministic in ``rng``.

    ``max_time`` is a hard cap: the jump that crosses it is not a first passage observed within the
    window, so it censors too. Testing the clock only before the jump returned times up to 4.4x the
    cap as uncensored answers, biasing the finite subsample upward.

    A run that ends without the species reaching zero — the ``max_time`` cap, or an absorbing state
    with no further reactions — returns ``inf``, because it observed no extinction. Returning ``t``
    made a censored run indistinguishable from a first passage, so a cap silently became the answer:
    an immigration-death process that never goes extinct reported a mean "extinction time" of 9.13
    at ``max_time=10`` against a true 39.2, and a network where the species can never reach zero
    returned a confident finite time on all 2000 runs and certified as reproduced. ``inf``
    poisons an average rather than flattering it, which is the direction this class errs in.
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
    return t if state[species] == 0 and t < max_time else float("inf")


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


#: What a noise claim reports, which is a *spread* statistic — the same shape a population's
#: inter-individual variability is, and computed by the same shared function so the two classes
#: cannot disagree about what a coefficient of variation is. Kept under this class's own name
#: because that is what its claims and its certificates say.
NoiseStatistic = SpreadStatistic


def _noise_statistic(values: Sequence[int], statistic: SpreadStatistic) -> float:
    """This class's spelling of :func:`reprolith.oracle.spread_statistic`."""
    return spread_statistic(values, statistic)


def noise_standard_error(
    values: Sequence[int], statistic: SpreadStatistic
) -> float | None:
    """This class's spelling of :func:`reprolith.oracle.spread_standard_error`.

    Kept as a name because it is exported and because "the noise statistic's own error bar" is what
    a stochastic certificate's protocol line calls it; the computation moved to the shared oracle
    when the population class needed the same error bar for the same reason.
    """
    return spread_standard_error(values, statistic)


@dataclass(frozen=True)
class NoiseClaim:
    """A published **noise statistic**: the Fano factor or coefficient of variation of a species.

    The class's fourth reproduction target, and the one that is about the *spread* rather than the
    centre of the distribution — which is what a stochastic model is for. Single-cell and
    gene-expression papers report it as their headline: a Fano factor of 1 says expression is
    constitutive, above 1 says it is bursty, and the coefficient of variation is the noise level
    itself. ``fano_factor`` and ``coefficient_of_variation`` have computed both since this class was
    written, checked against the Poisson laws (Fano = 1, CV = 1/sqrt(mean)); no claim could carry
    one.

    The protocol is the same as a mean count's — ``duration``, ``trajectories`` and ``seed`` make
    the run byte-reproducible — but the ensemble has to be *larger* for the same confidence, and
    the certificate says by how much rather than leaving it to be assumed: the statistic's own
    jackknife standard error is measured and reported on the protocol line, and an ensemble whose
    noise is too large to decide the claim abstains rather than publishing either verdict.
    """

    claim_id: str
    quantity: str
    species: int
    statistic: NoiseStatistic
    reported_value: float
    source_location: str
    duration: float
    trajectories: int
    seed: int
    tolerance: Tolerance | None = None
    assumption_qualified: bool = True
    shortfall: Attribution | None = field(default=None)

    def __post_init__(self) -> None:
        if self.trajectories < 2:
            raise ValueError(
                f"claim {self.claim_id!r} asks for {self.trajectories} trajectories: a noise "
                "statistic is a property of a sample's spread, and one draw has none"
            )
        if self.duration <= 0.0:
            raise ValueError(
                f"claim {self.claim_id!r} asks for a run of {self.duration!r} time units: an "
                "ensemble that never advances reports the initial state's spread, which is zero"
            )
        if self.reported_value <= 0.0:
            raise ValueError(
                f"claim {self.claim_id!r} reports {self.reported_value!r}: both statistics are "
                "non-negative ratios, and a reported zero says the sample has no spread at all — "
                "which is a statement about the sampling rather than about the model"
            )


def _noise_protocol(claim: NoiseClaim) -> str:
    """The run behind a noise verdict, in the form a reader can re-run.

    The statistic is named, not just the species: the same ensemble answers both, and two claims
    reading different statistics off one run had byte-identical protocols while disagreeing about
    the number.
    """
    return (
        f"SSA ensemble: {claim.trajectories} trajectories to t={claim.duration:g}, "
        f"seed {claim.seed}, read={claim.statistic.value} of species[{claim.species}]"
    )


def _judge_noise(
    claim: NoiseClaim,
    n_species: int,
    reactions: Sequence[Reaction],
    initial: Sequence[int],
) -> ClaimAssessment:
    """Run the claim's ensemble, judge its noise statistic, or say why this ensemble cannot.

    Three ways it abstains, and each is a different fact about the run:

    * every trajectory ended at zero, so both statistics divide by a zero mean and neither has a
      value here at all;
    * the ensemble has no spread and is too small for that to be a measurement rather than an
      accident — the same bar a mean is held to, and it matters more here, since a spread of zero
      *is* this claim's quantity and would publish a confident ``failed`` against a correct model;
    * the statistic's own jackknife standard error is more than half the pass threshold, the regime
      where a correct model routinely misses and a wrong one routinely passes.
    """
    ensemble = ensemble_final_counts(
        n_species, reactions, initial,
        duration=claim.duration, trajectories=claim.trajectories, seed=claim.seed,
    )
    values = [run[claim.species] for run in ensemble]
    protocol = _noise_protocol(claim)
    try:
        observed = _noise_statistic(values, claim.statistic)
    except ValueError as exc:
        return replace(
            not_evaluable(
                claim_id=claim.claim_id, quantity=claim.quantity,
                source_location=claim.source_location,
                reason=(
                    f"{exc}: every trajectory in this ensemble ended at zero copies, so there is "
                    "no mean to normalize the spread by. The claim is unjudged rather than judged "
                    "against a spread of zero, which would read as a measurement of the model"
                ),
                reference_kind=ReferenceKind.NUMERIC,
            ),
            protocol=protocol,
        )
    standard_error = noise_standard_error(values, claim.statistic)
    _, count_variance = species_mean_variance(ensemble, claim.species)
    reason = unresolvable_ensemble_reason(
        reported_mean=claim.reported_value,
        # The spread of the *counts*, which is what the zero-spread guard is about: an ensemble in
        # which every trajectory landed on the same number has a Fano factor of exactly zero, and
        # below `_SPREAD_IS_EVIDENCE` that is as likely an accident as a measurement.
        variance=count_variance,
        trajectories=len(values),
        observed_mean=observed,
        tolerance=claim.tolerance,
        # The error bar on a ratio of moments is not sqrt(variance/n), so it is supplied rather
        # than derived — one rule, two ways of measuring what feeds it.
        standard_error=standard_error,
        quantity_noun="reported value",
    )
    if reason is not None:
        return replace(
            not_evaluable(
                claim_id=claim.claim_id, quantity=claim.quantity,
                source_location=claim.source_location, reason=reason,
                reference_kind=ReferenceKind.NUMERIC,
            ),
            protocol=protocol,
        )
    assessment = judge_scalar(
        claim_id=claim.claim_id,
        quantity=claim.quantity,
        source_location=claim.source_location,
        reported=claim.reported_value,
        predicted=observed,
        tolerance=claim.tolerance,
        attribution=claim.shortfall or undetermined_shortfall(claim.quantity),
        assumption_qualified=claim.assumption_qualified,
    )
    if standard_error is not None:
        tol = claim.tolerance or default_tolerance(
            ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
        )
        protocol += (
            f" (sampling noise: the statistic's jackknife standard error is "
            f"{standard_error / claim.reported_value:.2%} of the reported value, against a "
            f"{tol.reproduced_within:.0%} pass threshold"
            + _settling_clause(
                reported=claim.reported_value, observed=observed,
                relative_sem=abs(standard_error / claim.reported_value),
                trajectories=len(values), tolerance=tol,
            )
            + ")"
        )
    return replace(assessment, protocol=protocol)


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
    "NoiseClaim",
    "NoiseStatistic",
    "coefficient_of_variation",
    "fano_factor",
    "noise_standard_error",
    "stochastic_dossier",
    "validate_stochastic",
    "ensemble_final_counts",
    "ensemble_percentile_bands",
    "gillespie",
    "gillespie_at_times",
    "solver_pin",
    "species_mean_variance",
    "time_to_extinction",
    "unresolvable_ensemble_reason",
]
