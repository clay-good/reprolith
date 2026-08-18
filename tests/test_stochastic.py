"""The stochastic (Gillespie SSA) model class (spec: stochastic-class).

Self-validated non-circularly against systems whose stochastic result is known in closed form — no
external tool, no fabricated data. The SSA is pure Python and deterministic under a pinned seed, so
these run in the core CI job and reproduce byte-for-byte.
"""

from __future__ import annotations

import math
import random

import pytest
from reprolith import (
    PercentileBand,
    Reaction,
    ReferenceKind,
    Verdict,
    ensemble_final_counts,
    ensemble_percentile_bands,
    gillespie,
    judge_distribution,
    judge_scalar,
    species_mean_variance,
)


def _poisson_quantile(lam: float, percentile: float) -> float:
    """The nearest-rank quantile of a Poisson(lam) distribution — pure-Python closed form."""
    if lam <= 0.0:
        return 0.0
    target = percentile / 100.0
    cdf = 0.0
    term = math.exp(-lam)
    k = 0
    while True:
        cdf += term
        if cdf >= target - 1e-12:
            return float(k)
        k += 1
        term *= lam / k


def _immigration_death(k: float, gamma: float) -> list[Reaction]:
    # ∅ -(k)-> A  (zero-order birth) ; A -(gamma)-> ∅  (first-order death).
    return [
        Reaction(rate=k, reactants=(), products=((0, 1),)),
        Reaction(rate=gamma, reactants=((0, 1),), products=()),
    ]


def test_immigration_death_reproduces_the_poisson_stationary_mean_and_variance() -> None:
    # The immigration-death process has a Poisson stationary distribution with mean = variance = k/γ.
    k, gamma = 10.0, 1.0
    analytic = k / gamma  # = 10 for both mean and variance
    ensemble = ensemble_final_counts(
        1, _immigration_death(k, gamma), [0], duration=40.0, trajectories=400, seed=20260807
    )
    mean, variance = species_mean_variance(ensemble, species=0)

    # Judge the reproduced mean against the closed-form value with the oracle, at a finite-sample
    # tolerance (SE of the mean ~ sqrt(10/400) ≈ 0.16, so ~5% covers it comfortably).
    verdict = judge_scalar(
        claim_id="A-mean", quantity="stationary mean copy number", source_location="closed-form Poisson",
        reported=analytic, predicted=mean,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    # The Poisson signature — variance equals the mean — is reproduced too (looser: variance is noisier).
    assert abs(variance - analytic) / analytic < 0.20


def test_immigration_death_reproduces_the_full_poisson_stationary_distribution() -> None:
    # Beyond mean and variance: the *entire* stationary distribution of the immigration-death
    # process is Poisson(λ = k/γ) — provable by detailed balance. A Pearson chi-square goodness-of-fit
    # of the ensemble against the exact PMF tests the whole shape (every moment), not just the first
    # two. Non-circular: the reference is the closed-form Poisson law; deterministic under the seed.
    k, gamma = 8.0, 1.0
    lam = k / gamma
    trajectories = 4000
    ensemble = ensemble_final_counts(
        1, _immigration_death(k, gamma), [0], duration=20.0, trajectories=trajectories, seed=20260807
    )
    counts = [c[0] for c in ensemble]

    def pmf(n: int) -> float:
        return math.exp(-lam) * lam**n / math.factorial(n)

    # Inner bins 4..13 individually; the sparse tails are pooled into the edge bins (n≤3 keyed by
    # `low`, n≥14 keyed by `high`) so every expected count stays ≥ 5 — the validity condition for the
    # chi-square approximation. All bin keys are integers.
    low, high = 3, 14
    observed: dict[int, int] = {}
    for n in counts:
        key = low if n <= low else high if n >= high else n
        observed[key] = observed.get(key, 0) + 1

    def expected(key: int) -> float:
        if key == low:
            return trajectories * sum(pmf(n) for n in range(low + 1))
        if key == high:
            return trajectories * (1.0 - sum(pmf(n) for n in range(high)))
        return trajectories * pmf(key)

    keys = list(range(low, high + 1))  # 3..14 inclusive → 12 bins
    chi_square = sum((observed.get(key, 0) - expected(key)) ** 2 / expected(key) for key in keys)

    # df = bins − 1 = 11. The upper-tail 0.99 critical value of χ²(11) is 24.72; a statistic below it
    # means the ensemble is consistent with Poisson at the 1% level — the fit is not rejected.
    assert len(keys) - 1 == 11
    assert chi_square < 24.72


def test_transient_poisson_percentile_envelope_is_reproduced() -> None:
    # Immigration-death started empty is Poisson at every time t with mean λ(t) = (k/γ)(1 - e^{-γt}).
    # So the analytical percentile envelope over time is exact — an independent, closed-form ground
    # truth for the distributional (population) oracle applied to a stochastic reproduction.
    k, gamma = 8.0, 1.0
    reactions = _immigration_death(k, gamma)
    times = [1.0, 2.0, 4.0, 7.0, 12.0]
    percentiles = [10.0, 50.0, 90.0]
    lam = [k / gamma * (1 - math.exp(-gamma * t)) for t in times]
    analytic = tuple(
        PercentileBand(p, tuple(_poisson_quantile(x, p) for x in lam)) for p in percentiles
    )
    simulated = ensemble_percentile_bands(
        1, reactions, [0], times, species=0,
        percentiles=percentiles, trajectories=2000, seed=42,
    )
    # A stochastic percentile envelope carries Monte-Carlo and discrete-count noise, so it is judged
    # at the distributional figure tolerance — under which it reproduces the closed-form envelope.
    verdict = judge_distribution(
        claim_id="A-envelope", quantity="transient percentile envelope",
        source_location="closed-form transient Poisson", reference=analytic, predicted=simulated,
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    assert verdict.verdict is Verdict.REPRODUCED
    assert verdict.assumption_qualified is True  # a population reproduction is qualified by default
    # The median band matches the analytical Poisson median exactly at every sample time.
    sim_median = next(b for b in simulated if b.percentile == 50.0)
    analytic_median = next(b for b in analytic if b.percentile == 50.0)
    assert sim_median.curve == analytic_median.curve


def test_reversible_reaction_reproduces_the_binomial_equilibrium_mean() -> None:
    # A <-> B with total N conserved: at equilibrium B ~ Binomial(N, kf/(kf+kr)), mean = N*kf/(kf+kr).
    n_total, kf, kr = 50, 3.0, 1.0
    reactions = [
        Reaction(rate=kf, reactants=((0, 1),), products=((1, 1),)),  # A -> B
        Reaction(rate=kr, reactants=((1, 1),), products=((0, 1),)),  # B -> A
    ]
    analytic_b = n_total * kf / (kf + kr)  # = 37.5
    ensemble = ensemble_final_counts(
        2, reactions, [n_total, 0], duration=30.0, trajectories=400, seed=1234
    )
    mean_b, _ = species_mean_variance(ensemble, species=1)
    verdict = judge_scalar(
        claim_id="B-eq", quantity="equilibrium mean of B", source_location="closed-form binomial",
        reported=analytic_b, predicted=mean_b,
    )
    assert verdict.verdict is Verdict.REPRODUCED


def test_conservation_is_respected_every_trajectory() -> None:
    # A <-> B conserves A+B on every single trajectory — a structural invariant of the SSA.
    reactions = [
        Reaction(rate=2.0, reactants=((0, 1),), products=((1, 1),)),
        Reaction(rate=1.0, reactants=((1, 1),), products=((0, 1),)),
    ]
    ensemble = ensemble_final_counts(2, reactions, [30, 0], duration=10.0, trajectories=50, seed=7)
    assert all(a + b == 30 for a, b in ensemble)


def test_direct_method_reproduces_its_two_defining_probabilities() -> None:
    # Gillespie's direct method rests on two exact laws, and every stochastic result above inherits
    # its correctness from them. This validates the *sampler itself*, not an outcome:
    #   (a) the time to the first reaction is Exponential(total propensity), so
    #       P(≥1 event by T) = 1 − e^{−a_total·T};
    #   (b) the firing reaction is chosen with probability proportional to its propensity.
    # Two competing zero-order immigrations making distinct species make both observable from the
    # final counts alone. Non-circular: the reference is the algorithm's definition; seed-pinned.
    a, b = 3.0, 1.0
    reactions = [
        Reaction(rate=a, reactants=(), products=((0, 1),)),  # ∅ -> A
        Reaction(rate=b, reactants=(), products=((1, 1),)),  # ∅ -> B
    ]
    total = a + b
    duration = 0.1  # short, so most trajectories see zero or one event
    trajectories = 20000
    ensemble = ensemble_final_counts(
        2, reactions, [0, 0], duration=duration, trajectories=trajectories, seed=20260807
    )

    # (a) waiting-time law: fraction of runs with any event matches the exponential CDF.
    fired = sum(1 for a_count, b_count in ensemble if a_count + b_count >= 1) / trajectories
    assert abs(fired - (1 - math.exp(-total * duration))) < 0.01  # ~3 SE at n=20000

    # (b) selection law: among single-event runs, the event is A with probability a/(a+b).
    single = [(a_count, b_count) for a_count, b_count in ensemble if a_count + b_count == 1]
    fraction_a = sum(1 for a_count, _ in single if a_count == 1) / len(single)
    assert abs(fraction_a - a / total) < 0.02  # ~3 SE


def test_pinned_seed_is_byte_reproducible() -> None:
    reactions = _immigration_death(5.0, 1.0)
    a = ensemble_final_counts(1, reactions, [0], duration=20.0, trajectories=100, seed=99)
    b = ensemble_final_counts(1, reactions, [0], duration=20.0, trajectories=100, seed=99)
    assert a == b  # identical ensembles from the same seed — the reproducible-sampling contract


def test_absorbing_state_halts_the_trajectory() -> None:
    # Pure death with no birth drains to zero and then cannot fire — the run must terminate cleanly.
    death_only = [Reaction(rate=1.0, reactants=((0, 1),), products=())]
    final = gillespie(1, death_only, [5], duration=1e6, rng=random.Random(0))
    assert final == [0]


def test_dimerization_propensity_uses_the_falling_factorial() -> None:
    # 2A -> A2: propensity = rate * n(n-1)/2. With n=4 and rate=1, that is 6.
    dimerize = Reaction(rate=1.0, reactants=((0, 2),), products=((1, 1),))
    assert dimerize.propensity([4, 0]) == pytest.approx(6.0)
    assert dimerize.propensity([1, 0]) == 0.0  # cannot fire with a single molecule


def test_certify_stochastic_produces_a_qualified_reproduced_certificate() -> None:
    from reprolith import (
        EnginePin,
        OverallVerdict,
        PaperIdentity,
        StochasticClaim,
        certify_stochastic,
    )

    k, gamma = 10.0, 1.0
    cert = certify_stochastic(
        paper=PaperIdentity(title="An immigration-death process", doi="10.0/id"),
        engine_pin=EnginePin(engine="reprolith-ssa", version="0.0.1"),
        n_species=1, reactions=_immigration_death(k, gamma), initial=[0],
        claims=[StochasticClaim(
            claim_id="A-mean", quantity="stationary mean copy number", species=0,
            reported_mean=k / gamma, source_location="closed-form Poisson",
            duration=40.0, trajectories=400, seed=20260807,
        )],
    )
    assert cert.assessments[0].verdict is Verdict.REPRODUCED
    assert cert.assessments[0].assumption_qualified is True  # sampling-dependent
    # Reproduced but qualified by the sampling dependence -> the certificate cannot round up to clean.
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert cert.scope.machine  # the scope flag travels with a stochastic certificate too
    # The qualification names what it qualifies. A flag reading "this rests on an assumption
    # Reprolith supplied" while listing none is indistinguishable from a missing record; the
    # ensemble is the assumption, and it is on the certificate as one.
    assumption = cert.assumptions[0]
    assert assumption.id == "ssa-sampling-A-mean"
    assert assumption.chosen == "SSA ensemble: 400 trajectories to t=40, seed 20260807"
    assert assumption.load_bearing is True and assumption.attributed_to == "reprolith"


def test_stochastic_dossier_records_species_reactions_and_sampling_gap() -> None:
    from reprolith import (
        DossierClaim,
        Equation,
        GapKind,
        Parameter,
        stochastic_dossier,
    )

    dossier = stochastic_dossier(
        "immigration-death",
        species={"A": 0},
        reactions=[Equation(target="birth", expression="k", source_location="Eq 1"),
                   Equation(target="death", expression="gamma*A", source_location="Eq 2")],
        rates=[Parameter(name="k", value=10.0, unit="1/time", source_location="Table 1"),
               Parameter(name="gamma", value=1.0, unit="1/time", source_location="Table 1")],
        source_location="Table 1", sampling_stated=False,
        claims=[DossierClaim(id="mean", quantity="stationary mean", conditions="", source_location="Fig 1")],
    )
    assert dossier.state_variables == ("A",)
    assert dossier.initial_conditions[0].name == "A"
    # An unstated sampling protocol is a load-bearing gap.
    assert len(dossier.load_bearing_gaps()) == 1
    assert dossier.load_bearing_gaps()[0].kind is GapKind.SAMPLING


def test_poisson_fano_factor_and_noise_scaling_law() -> None:
    # The immigration-death process is Poisson at stationarity, so its Fano factor (variance/mean)
    # is 1 and its coefficient of variation scales as 1/sqrt(mean) — the fundamental law that
    # smaller molecule populations are proportionally noisier. Both are famous, closed-form results.
    from reprolith import coefficient_of_variation, fano_factor

    for k in (4.0, 16.0, 64.0):  # stationary mean = k/gamma = k
        ensemble = ensemble_final_counts(
            1, _immigration_death(k, 1.0), [0], duration=40.0, trajectories=800, seed=int(k) * 7
        )
        fano = fano_factor(ensemble, 0)
        cv = coefficient_of_variation(ensemble, 0)
        assert abs(fano - 1.0) < 0.15  # Poisson signature: variance == mean
        # CV * sqrt(mean) == 1 for Poisson; check the 1/sqrt(mean) scaling holds across sizes.
        assert abs(cv * math.sqrt(k) - 1.0) < 0.12


def test_bursty_production_reproduces_the_super_poissonian_fano_law() -> None:
    # Production in bursts of size b (immigration of b molecules at a time), with first-order death,
    # gives super-Poissonian noise with Fano factor (b+1)/2 — the closed-form signature of bursty
    # gene expression, reducing to Poisson (Fano 1) when b=1.
    from reprolith import fano_factor

    k, gamma = 5.0, 1.0
    for b in (1, 2, 4):
        reactions = [
            Reaction(rate=k, reactants=(), products=((0, b),)),  # burst of b
            Reaction(rate=gamma, reactants=((0, 1),), products=()),
        ]
        ensemble = ensemble_final_counts(
            1, reactions, [0], duration=40.0, trajectories=1500, seed=b * 13
        )
        mean, _ = species_mean_variance(ensemble, 0)
        assert abs(mean - b * k / gamma) / (b * k / gamma) < 0.05  # mean = b·k/γ
        analytic_fano = (b + 1) / 2
        assert abs(fano_factor(ensemble, 0) - analytic_fano) < 0.15  # Fano = (b+1)/2


def test_pure_death_reproduces_the_harmonic_extinction_time() -> None:
    # For a pure-death process, each of N0 molecules dies independently at rate gamma, so the
    # population's extinction time is the maximum of N0 exponentials, with mean (1/gamma)*H_{N0}
    # (the N0-th harmonic number). A clean first-passage result for small-population extinction.
    from reprolith import judge_scalar, time_to_extinction

    gamma, n0 = 1.0, 8
    harmonic = math.fsum(1.0 / m for m in range(1, n0 + 1))
    analytic_mean = harmonic / gamma  # ~ 2.718
    death = [Reaction(rate=gamma, reactants=((0, 1),), products=())]
    rng = random.Random(20260807)
    times = [time_to_extinction(1, death, [n0], species=0, rng=rng) for _ in range(3000)]
    measured_mean = math.fsum(times) / len(times)
    verdict = judge_scalar(
        claim_id="extinction", quantity="mean extinction time", source_location="H_{N0}/gamma",
        reported=analytic_mean, predicted=measured_mean,
    )
    assert verdict.verdict is Verdict.REPRODUCED  # within the 5% default for 3000 trajectories


def test_ensemble_percentile_bands_rejects_an_empty_ensemble() -> None:
    # Zero trajectories has no distribution to take percentiles of. The house style is a typed
    # abstention (like species_mean_variance's "need at least one trajectory"), not an IndexError
    # leaking out of the nearest-rank percentile.
    birth = [Reaction(rate=1.0, reactants=(), products=((0, 1),))]
    with pytest.raises(ValueError, match="at least one trajectory"):
        ensemble_percentile_bands(
            1, birth, [0], [0.0, 1.0], species=0, percentiles=[50.0], trajectories=0, seed=1
        )


def test_a_negative_or_non_finite_rate_is_refused_rather_than_freezing_every_trajectory() -> None:
    # A negative rate makes the total propensity non-positive, so the SSA treats the initial state
    # as absorbing and every trajectory returns it unchanged. The reported "prediction" is then the
    # initial condition — a finite number, so the oracle's non-finite guard cannot see it — and a
    # model whose rate carries the wrong sign certifies as a perfect reproduction. Refuse instead.
    for bad in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite and non-negative"):
            Reaction(rate=bad, reactants=((0, 1),), products=((1, 1),))
    # Zero stays legal: a disabled reaction is a modelling choice, not a broken rate.
    assert Reaction(rate=0.0, reactants=((0, 1),), products=((1, 1),)).propensity([5, 0]) == 0.0


def test_a_species_repeated_in_the_reactants_is_refused() -> None:
    # Two entries for one species would each contribute their own falling factorial (k*n*n instead
    # of the dimerization k*n(n-1)/2) and consume the species twice per firing, which drives counts
    # negative. The single stoichiometry form is the only correct encoding.
    with pytest.raises(ValueError, match="appears twice"):
        Reaction(rate=1.0, reactants=((0, 1), (0, 1)), products=((1, 1),))


def test_ensemble_final_counts_rejects_an_empty_ensemble() -> None:
    # Mirrors the percentile-band guard: zero trajectories silently returned [], which then failed
    # far away in species_mean_variance instead of at the request that was wrong.
    birth = [Reaction(rate=1.0, reactants=(), products=((0, 1),))]
    with pytest.raises(ValueError, match="at least one trajectory"):
        ensemble_final_counts(1, birth, [0], duration=1.0, trajectories=0, seed=1)


def test_gillespie_max_events_bounds_a_runaway_trajectory() -> None:
    # The event count of an SSA run is ∫propensity dt, which a caller drives through BOTH the
    # duration and the network's rates — so a huge duration (or rate) can run unboundedly. The
    # optional max_events safety valve refuses rather than looping forever; without it the same
    # request would never return. A constant-propensity birth reaction never depletes, so it
    # fires without limit until the cap trips.
    birth = [Reaction(rate=1000.0, reactants=(), products=((0, 1),))]
    rng = random.Random(1)
    with pytest.raises(ValueError, match="exceeded"):
        gillespie(1, birth, [0], duration=1e12, rng=rng, max_events=10_000)
    # The default (None) preserves the unbounded library contract for a normal, finite run.
    final = gillespie(1, birth, [0], duration=0.01, rng=random.Random(1))
    assert final[0] >= 0


def test_a_stochastic_certificate_records_the_sampling_that_produced_it() -> None:
    # A sampled number nobody can re-run is not evidence: the certificate reported a discrepancy
    # with no seed, trajectory count, or duration anywhere in it, so a third party could not
    # reproduce the figure and a seed that merely happened to agree left no trace. The spec asks
    # for the seed and trajectory count as part of the claim's protocol.
    from reprolith import EnginePin, PaperIdentity, StochasticClaim, certify_stochastic

    reactions = _immigration_death(10.0, 1.0)
    cert = certify_stochastic(
        paper=PaperIdentity(title="Immigration-death", doi="10.1/imm"),
        engine_pin=EnginePin(engine="reprolith-ssa", version="0.0.1"),
        n_species=1, reactions=reactions, initial=[0],
        claims=[StochasticClaim(
            claim_id="c1", quantity="mean copy number", source_location="closed-form",
            species=0, reported_mean=10.0, duration=40.0, trajectories=400, seed=20260807,
        )],
    )
    protocol = cert.assessments[0].protocol
    assert protocol is not None
    assert "400" in protocol and "20260807" in protocol and "40" in protocol
    assert cert.content()["assessments"][0]["protocol"] == protocol

    # A deterministic class carries no protocol, and its content keeps the shape it always had —
    # so no previously published certificate is re-digested by this field existing.
    plain = judge_scalar(
        claim_id="c1", quantity="AUC", source_location="Table 1", reported=1.0, predicted=1.0,
    )
    assert plain.protocol is None
    assert "protocol" not in plain.to_dict()


def test_a_duration_the_run_cannot_advance_through_is_refused() -> None:
    # Same failure mode as a broken rate, reached through the other caller-supplied number: with a
    # NaN or negative duration the loop never runs, the ensemble returns the initial state, and a
    # claim reporting the initial condition is judged a perfect reproduction of a simulation that
    # never happened. Duration is caller-supplied at the untrusted linter boundary.
    decay = [Reaction(rate=1.0, reactants=((0, 1),), products=((1, 1),))]
    for bad in (float("nan"), float("inf"), -5.0):
        with pytest.raises(ValueError, match="finite, non-negative duration"):
            ensemble_final_counts(2, decay, [100, 0], duration=bad, trajectories=5, seed=1)
    # A zero duration is a well-defined request for the initial state, and stays legal.
    assert ensemble_final_counts(
        2, decay, [100, 0], duration=0.0, trajectories=2, seed=1
    ) == [[100, 0], [100, 0]]


def test_negative_initial_counts_and_out_of_order_sample_times_are_refused() -> None:
    decay = [Reaction(rate=1.0, reactants=((0, 1),), products=((1, 1),))]
    with pytest.raises(ValueError, match="non-negative"):
        ensemble_final_counts(2, decay, [-5, 0], duration=1.0, trajectories=2, seed=1)
    # "times must be non-decreasing" was documented but unchecked, so a backwards sample time read
    # a state the trajectory had already left, returning an envelope that never happened.
    with pytest.raises(ValueError, match="non-decreasing"):
        ensemble_percentile_bands(
            2, decay, [10, 0], [0.0, 5.0, 1.0], species=0,
            percentiles=[50.0], trajectories=2, seed=1,
        )


def test_a_seed_that_misses_certifies_honestly_instead_of_raising() -> None:
    # A claim supplying no root-cause attribution used to raise when its verdict was not
    # reproduced, so a seed that happened to miss crashed the run rather than producing the
    # not-reproduced certificate it had earned — and a class that can only ever emit a clean
    # verdict or a stack trace has a self-validation record that means nothing.
    from reprolith import EnginePin, PaperIdentity, Reaction, StochasticClaim, certify_stochastic

    reactions = [Reaction(10.0, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())]  # mean 10 at steady state
    verdicts = set()
    for seed in range(1, 41):
        cert = certify_stochastic(
            paper=PaperIdentity(title="t", doi=""), engine_pin=EnginePin(engine="reprolith-ssa", version="1"),
            n_species=1, reactions=reactions, initial=[0],
            claims=[StochasticClaim(claim_id="m", quantity="mean count", species=0,
                                    reported_mean=10.0, source_location="closed form",
                                    duration=40.0, trajectories=400, seed=seed)],
        )
        verdicts.add(cert.overall.value)
    # Both outcomes occur across seeds, and neither raises.
    assert verdicts == {"partially-reproduced", "not-reproduced"}


def test_an_ensemble_too_small_to_resolve_the_claim_abstains_instead_of_failing() -> None:
    # The tolerance is fixed; the noise around the mean is not — the caller sets it with the
    # trajectory count. At ten trajectories a provably correct immigration-death model fails its
    # 5% claim on most seeds, so the class published `not-reproduced` against an author whose
    # model is exactly right. Where the ensemble's standard error is comparable to the pass
    # threshold, "this ensemble cannot resolve the claim" is the true statement.
    from reprolith import EnginePin, PaperIdentity
    from reprolith.stochastic import Reaction, StochasticClaim, certify_stochastic

    reactions = [
        Reaction(rate=6.0, reactants=(), products=((0, 1),)),
        Reaction(rate=1.5, reactants=((0, 1),), products=()),
    ]  # stationary mean 4, exactly
    pin = EnginePin(engine="reprolith-ssa", version="0.0.1")

    def certify(trajectories: int, seed: int):
        return certify_stochastic(
            paper=PaperIdentity(title="Immigration-death"),
            engine_pin=pin, n_species=1, reactions=reactions, initial=[0],
            claims=[StochasticClaim(
                claim_id="mean", quantity="mean copy number", source_location="closed-form",
                species=0, reported_mean=4.0, duration=40.0,
                trajectories=trajectories, seed=seed,
            )],
        )

    thin = certify(10, seed=7)
    assert thin.assessments[0].verdict.value == "not-evaluable"
    assert "cannot resolve" in (thin.assessments[0].root_cause or "")
    # The sampling that could not resolve it is still recorded, so the fix is visible.
    assert "10 trajectories" in (thin.assessments[0].protocol or "")
    # A big enough ensemble judges the claim normally.
    thick = certify(1600, seed=11)
    assert thick.assessments[0].verdict.value == "reproduced"


def test_a_single_trajectory_cannot_resolve_a_claim() -> None:
    """Zero variance means "resolvable" only when the ensemble was big enough to measure one.

    One draw has a population variance of 0 by construction, so the standard-error guard was
    skipped exactly where the sampling noise is largest: an exactly-correct model published
    `reproduced` or `failed` by seed lottery, while every ensemble size from 2 upward abstained.
    """
    from reprolith.stochastic import unresolvable_ensemble_reason

    reason = unresolvable_ensemble_reason(variance=0.0, reported_mean=10.0, trajectories=1)
    assert reason is not None and "single draw" in reason
    # A genuinely resolvable ensemble is still resolvable.
    assert unresolvable_ensemble_reason(variance=8.9, reported_mean=10.0, trajectories=1000) is None
