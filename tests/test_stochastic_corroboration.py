"""A second engine for the stochastic class: libRoadRunner's Gillespie against this package's SSA.

This was the last class whose certificates rested on one implementation, and the roadmap recorded
the reason as an absence of any other: "a Gillespie ensemble" was said to be a question no
installed implementation but this one answers. That was never checked — libRoadRunner ships a
Gillespie integrator, it was already pinned here as the ODE classes' second engine, and it runs
these networks in under a second.

What it reports is different in kind from the other three classes, and that is the substance here
rather than the plumbing. Two engines that solve an ODE or a linear program agree to their last
digits; two *ensembles* of the same model agree only up to Monte Carlo error. So the comparison is
a count of combined standard errors, and a pass carries the size of the bias it could have seen —
because two small ensembles agree with almost anything.

Needs the ``engine`` extra (python-libsbml) and the ``corroborate`` extra (libRoadRunner).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
pytest.importorskip("roadrunner", reason="the 'corroborate' extra (libRoadRunner) is not installed")

from reprolith import (  # noqa: E402
    build_stochastic_sbml,
    corroborate_ensemble_mean,
    ingest_stochastic_sbml,
)
from reprolith.query import corroboration_held, corroboration_summary  # noqa: E402
from reprolith.stochastic import Reaction  # noqa: E402

_MILESTONE = Path(__file__).parent.parent / "datasets" / "stochastic" / "milestone"

#: The three networks the stochastic milestone certifies, at the protocol each was certified under.
_SYSTEMS = {
    "immigration_death_10": (
        ["S0"], [Reaction(10.0, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())], [0], 0, 40.0, 400,
        20260807,
    ),
    "immigration_death_4": (
        ["S0"], [Reaction(6.0, (), ((0, 1),)), Reaction(1.5, ((0, 1),), ())], [0], 0, 40.0, 1600, 11,
    ),
    "reversible_isomerization": (
        ["S0", "S1"],
        [Reaction(3.0, ((0, 1),), ((1, 1),)), Reaction(1.0, ((1, 1),), ((0, 1),))],
        [50, 0], 1, 30.0, 400, 1234,
    ),
}


def _committed() -> dict:
    return json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", sorted(_SYSTEMS))
def test_each_certified_network_agrees_with_libroadrunners_gillespie(key: str) -> None:
    """The committed record is reproduced, not merely present.

    Read off the file rather than recomputed into it: a change to the sampler that moved these
    ensembles apart would otherwise regenerate a passing record instead of failing.

    Every field but the engine builds, and that exclusion is the record's own rule rather than a
    convenience — a committed record must keep naming the build it was measured on, not borrow the
    one installed today, or a stale bound reads as a fresh one. The builds are checked on their
    own below.

    What survives the exclusion is worth stating: these numbers were measured under libRoadRunner
    2.7.0 and CI runs 2.10.0, and the published standard errors and resolutions are identical to
    the last digit across both. A Monte Carlo statistic that moved between machines would be
    unpublishable, and this one does not.
    """
    species, reactions, initial, observed, duration, trajectories, seed = _SYSTEMS[key]
    result = corroborate_ensemble_mean(
        species, reactions, initial, observed=observed,
        duration=duration, trajectories=trajectories, seed=seed,
    )
    assert result.stable, result.summary()
    measured = {k: v for k, v in result.record().items() if k != "engine_versions"}
    committed = {k: v for k, v in _committed()[key].items() if k != "engine_versions"}
    assert measured == committed


def test_the_record_names_the_builds_it_was_measured_on() -> None:
    """A corroboration bound carries a certificate's weight, and one naming no software could not
    be told from a current one. Reprolith's own side names the revision of the code that ran."""
    for key, row in _committed().items():
        assert all(version for version in row["engine_versions"]), key
        assert "rev " in row["engine_versions"][0], key


def test_the_comparison_is_standard_errors_and_not_a_distance() -> None:
    """A z-score is not a curve distance, and must never be published on that scale.

    Rounded to a decade, the immigration-death agreement of 1.9 standard errors would read as
    "engine-independent to 2e+00" — beside the kinetic class's 1e-03, a reader would take it for
    a catastrophic disagreement. It is the same field, so the *comparison* has to carry it.
    """
    record = _committed()["immigration_death_10"]
    assert record["comparison"] == "monte-carlo-agreement"
    assert 0.0 < record["distance_at_most"] <= 3.0
    held = corroboration_held(
        corroboration_summary({"stochastic": _committed()})["by_class"]["stochastic"]
    )
    assert "combined standard errors" in held
    assert "e-0" not in held


def test_a_pass_carries_the_bias_it_could_not_have_seen() -> None:
    """Two ensembles agree at any criterion if they are small enough.

    So the honest number beside the agreement is the smallest true discrepancy it could have
    resolved. On the Poisson-mean-10 network that is 6.5% of the mean, against the 5% the class's
    own scalar verdict passes at — this corroboration is *weaker* than the verdict it stands
    beside, and the record says so instead of reading as a clean confirmation.
    """
    committed = _committed()
    assert committed["immigration_death_10"]["resolves_bias_above"] > 0.05
    assert committed["reversible_isomerization"]["resolves_bias_above"] < 0.02
    summary = corroboration_summary({"stochastic": committed})["by_class"]["stochastic"]
    # The class's weakest resolution, not its best: a summary that quoted the 1.8% would say the
    # class resolves a bias three times smaller than its worst entry can.
    assert summary["resolves_bias_above"] == max(
        row["resolves_bias_above"] for row in committed.values()
    )


def test_a_deterministic_network_reports_engine_names_and_not_build_strings() -> None:
    """The branch no committed record reaches, and where the drift was.

    A network with nothing left to do has zero variance on both sides, so there is no sampling
    error to standardize by and the comparison falls back to an exact match. That branch built the
    `engines` pair out of the *build* string, so a record from it would have named an engine called
    "gillespie-direct-method (rev ...)" — and `engines` is the key the registry line, the terminal
    column and the per-class pair check are all read from. Held here because no milestone reaches
    it; see `tests/test_corroboration_contract.py` for the invariant across all six front-ends.
    """
    # An empty network from an empty state: both samplers return the initial count, every time.
    result = corroborate_ensemble_mean(
        ["A"], [], [7], observed=0, duration=5.0, trajectories=20, seed=1,
    )
    assert result.comparison == "exact-match"
    assert result.stable, result.summary()
    assert result.engines == ("reprolith-ssa", "roadrunner-gillespie")
    assert "rev " in result.versions[0], result.versions
    assert "rev " not in result.engines[0]


def test_a_higher_order_reaction_is_refused_rather_than_compared() -> None:
    """The two samplers do not model the same system above first order.

    Reprolith runs the stochastic mass action k·n(n−1)/2; libRoadRunner's Gillespie takes the SBML
    rate law as the propensity and runs k·n². On 2A → B from four molecules that is a 24% gap in
    the mean, which is real and is not the solvers disagreeing. Published, it would blame the
    wrong thing — and it is exactly the shape a corroboration is supposed to catch, so it has to
    be refused by name rather than reported.
    """
    with pytest.raises(ValueError, match="at most first-order"):
        corroborate_ensemble_mean(
            ["A", "B"], [Reaction(0.5, ((0, 2),), ((1, 1),))], [4, 0],
            observed=1, duration=0.3, trajectories=50, seed=3,
        )


def test_a_seeded_comparison_is_reproducible_on_both_sides() -> None:
    """Both ensembles are a deterministic function of the seed, or the record is a lottery.

    Reprolith's SSA already promised this; libRoadRunner's integrator has its own generator, and
    a milestone that re-published a different agreement on every run would make the committed
    number unfalsifiable.
    """
    species, reactions, initial, observed, duration, _, seed = _SYSTEMS["immigration_death_10"]
    kwargs = dict(observed=observed, duration=duration, trajectories=120, seed=seed)
    first = corroborate_ensemble_mean(species, reactions, initial, **kwargs)
    again = corroborate_ensemble_mean(species, reactions, initial, **kwargs)
    assert first.record() == again.record()
    other = corroborate_ensemble_mean(
        species, reactions, initial, **{**kwargs, "seed": seed + 1}
    )
    assert other.distance != first.distance, "the seed changed nothing; one side is not sampling"


@pytest.mark.parametrize(
    "species,reactions,initial",
    [
        (["A"], [Reaction(10.0, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())], [0]),
        (["A", "B"], [Reaction(0.5, ((0, 2),), ((1, 1),))], [100, 0]),
        (["A", "B", "C"], [Reaction(2.0, ((0, 1), (1, 1)), ((2, 1),))], [30, 40, 0]),
    ],
)
def test_the_network_the_second_engine_runs_is_the_one_this_one_runs(
    species: list[str], reactions: list[Reaction], initial: list[int]
) -> None:
    """Round-trip: what the writer emits, the reader returns unchanged.

    This is what makes the comparison a statement about two samplers rather than about two
    encodings. The rate conversion is the part that can silently differ — a `Reaction` carries the
    stochastic constant and an SBML law states the deterministic one — so the dimerization case is
    the one that matters: written verbatim it would reach the second engine at twice its rate.
    """
    written = build_stochastic_sbml(species, reactions, initial)
    names, parsed, counts = ingest_stochastic_sbml(written)
    assert names == species
    assert counts == initial
    assert [(r.rate, r.reactants, r.products) for r in parsed] == [
        (r.rate, r.reactants, r.products) for r in reactions
    ]


def test_the_writer_refuses_a_network_whose_names_and_counts_are_out_of_step() -> None:
    """One fewer count than species does not mean the last species starts at zero.

    Zipped, it would silently drop the last species' initial amount and emit a model that runs.
    """
    with pytest.raises(ValueError, match="out of step"):
        build_stochastic_sbml(["A", "B"], [], [5])
