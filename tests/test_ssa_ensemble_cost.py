"""What a *correct* stochastic model costs at the ensemble sizes this repository publishes.

Every other tolerance in [`docs/discipline-loop.md`](../docs/discipline-loop.md) has a measured
cost beside it. The stochastic class's did not, and it is the class where the cost is largest: its
claims are judged at the scalar 5% / 15%, and the number being judged is the mean of an ensemble
Reprolith itself sampled. Draw the *right* model twice and that mean moves.

`unresolvable_ensemble_reason` already refuses to publish a verdict when the standard error of the
mean is more than half the pass threshold. What nothing said is what that rule buys. It compares
two quantities that both scale with the reported mean, so the answer is one number for every model:
on the boundary the pass band is exactly two standard errors wide either side, and a correct
ensemble lands outside it 4.6% of the time.

Measured, not asserted. The ensembles are drawn here from each model's own stationary
distribution, the miss rate is counted, and the closed form is checked against the count rather
than standing in for it. The trajectory counts are read out of the committed certificates, so an
ensemble that shrinks in a regenerated milestone is caught here rather than in a reader's
inference. Pure stdlib and seeded: the same number on every machine.
"""

from __future__ import annotations

import math
import random
import re
from pathlib import Path
from statistics import NormalDist

#: The class default a stochastic mean claim is judged at.
_PASS = 0.05

_REPLICATES = 2000

_CERTIFICATES = Path(__file__).parent.parent / "datasets" / "stochastic" / "milestone" / "certificates"

#: Each committed entry's stationary distribution, from the model its own title states.
#:
#: * immigration-death at rate k with decay γ is Poisson(k/γ): mean and variance both k/γ.
#: * reversible isomerization of N molecules with kf/kr is Binomial(N, kf/(kf+kr)) in B, so the
#:   mean is Np and the variance Np(1−p) — narrower than a Poisson of the same mean, which is why
#:   it has the most headroom of the three.
_MODELS = {
    "immigration_death_10": ("poisson", 10.0),      # k=10, γ=1
    "immigration_death_4": ("poisson", 4.0),        # k=6, γ=1.5
    "reversible_isomerization": ("binomial", (50, 0.75)),  # N=50, kf=3, kr=1
}

_TRAJECTORIES = re.compile(r"SSA ensemble: (\d+) trajectories")


def _committed_trajectories() -> dict[str, int]:
    counts = {}
    for name in _MODELS:
        text = (_CERTIFICATES / f"{name}.txt").read_text(encoding="utf-8")
        match = _TRAJECTORIES.search(text)
        assert match, f"{name} publishes no trajectory count for this to be measured against"
        counts[name] = int(match.group(1))
    return counts


def _moments(kind: str, parameters: object) -> tuple[float, float]:
    if kind == "poisson":
        mean = float(parameters)  # type: ignore[arg-type]
        return mean, mean
    size, probability = parameters  # type: ignore[misc]
    return size * probability, size * probability * (1.0 - probability)


def _draw(rng: random.Random, kind: str, parameters: object) -> int:
    if kind == "poisson":
        limit, count, product = math.exp(-float(parameters)), 0, rng.random()  # type: ignore[arg-type]
        while product > limit:
            count += 1
            product *= rng.random()
        return count
    size, probability = parameters  # type: ignore[misc]
    return sum(1 for _ in range(size) if rng.random() < probability)


def _outcomes(kind: str, parameters: object, trajectories: int, seed: int) -> tuple[int, int, int]:
    """How many replicates abstain, pass and miss — for a model that is exactly right."""
    from reprolith.stochastic import unresolvable_ensemble_reason

    mean, _variance = _moments(kind, parameters)
    rng = random.Random(seed)
    abstained = passed = missed = 0
    for _ in range(_REPLICATES):
        draws = [_draw(rng, kind, parameters) for _ in range(trajectories)]
        sample = math.fsum(draws) / trajectories
        # The population variance of the draws, as `species_mean_variance` computes it.
        variance = math.fsum((d - sample) ** 2 for d in draws) / trajectories
        if unresolvable_ensemble_reason(
            reported_mean=mean, variance=variance,
            trajectories=trajectories, observed_mean=sample,
        ):
            abstained += 1
        elif abs(sample - mean) / mean <= _PASS:
            passed += 1
        else:
            missed += 1
    return abstained, passed, missed


def _standard_errors_of_headroom(kind: str, parameters: object, trajectories: int) -> float:
    """How many standard errors of the mean separate the true value from the pass band's edge."""
    mean, variance = _moments(kind, parameters)
    return _PASS * mean / math.sqrt(variance / trajectories)


def test_every_committed_stochastic_entry_has_room_to_be_right() -> None:
    """Each published entry, at the ensemble size its own certificate names.

    Three standard errors is where the class's other measured rule already sits
    (`_DECISIVELY_OUTSIDE`), and it is the point past which a correct model is published wrongly
    less than one time in three hundred.
    """
    counts = _committed_trajectories()
    headroom = {
        name: _standard_errors_of_headroom(*_MODELS[name], counts[name]) for name in _MODELS
    }
    assert all(value >= 3.0 for value in headroom.values()), headroom
    # Not all alike, and the spread is the point: the binomial entry's variance is a quarter of a
    # Poisson of the same mean, so the same 400 trajectories buy it four times the headroom.
    assert headroom["reversible_isomerization"] > headroom["immigration_death_10"]


def test_what_a_correct_model_costs_at_the_sizes_this_repository_published() -> None:
    counts = _committed_trajectories()
    for index, name in enumerate(sorted(_MODELS)):
        kind, parameters = _MODELS[name]
        abstained, passed, missed = _outcomes(kind, parameters, counts[name], seed=90001 + index)
        judged = passed + missed
        assert abstained == 0, (name, abstained)
        # Fewer than one in three hundred, on every committed entry, and that is the whole claim:
        # what these certificates rest on is not close to the edge of what the ensemble can decide.
        assert missed / judged < 0.005, (name, missed, judged)


def test_the_closed_form_matches_the_ensembles_actually_drawn() -> None:
    """At the guard's own boundary, where the rate is large enough to count."""
    # Poisson(4) at 400 trajectories: a relative standard error of 0.025 against a 0.05 threshold,
    # which is exactly where `unresolvable_ensemble_reason` stops abstaining.
    assert abs(_standard_errors_of_headroom("poisson", 4.0, 400) - 2.0) < 1e-9
    abstained, passed, missed = _outcomes("poisson", 4.0, 400, seed=770)
    judged = passed + missed
    predicted = 2.0 * (1.0 - NormalDist().cdf(2.0))
    band = 4.0 * math.sqrt(predicted * (1 - predicted) / judged)
    assert abs(missed / judged - predicted) <= band, (missed, judged, predicted)
    # Sitting *on* the boundary, the guard is deciding on a sample variance that straddles it, so
    # about half of these ensembles abstain rather than publishing at all. That is the honest
    # behaviour, and it is why the committed entries are three standard errors clear of it.
    assert 0.3 < abstained / _REPLICATES < 0.7, abstained


def test_the_guards_cost_is_one_number_for_every_model() -> None:
    """Why the boundary is worth stating once rather than per entry: it is a ratio.

    Both sides of `relative standard error <= half the pass threshold` scale with the reported
    mean, so an ensemble on the boundary is two standard errors from the edge of the pass band
    whatever the model is. 4.6% of correct ensembles land outside it; at three it is 0.3%.
    """
    assert abs(2.0 * (1.0 - NormalDist().cdf(2.0)) - 0.0455) < 0.001
    assert 2.0 * (1.0 - NormalDist().cdf(3.0)) < 0.003
