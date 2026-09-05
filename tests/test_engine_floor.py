"""What choosing an engine costs, before the reconstruction disagrees with anything.

Every other "what the method spends" measurement in the [loop record](../docs/discipline-loop.md)
is about a step between the paper and the verdict: reading a curve off a picture, drawing a
population, re-fitting from noisy data. This one is about the last step, and it is the only one
already measured on the committed corpus rather than on synthetic inputs — it just was never
expressed in the units the verdict is expressed in.

Cross-engine corroboration re-runs a certified result under a second independent simulator and
publishes the normalized distance between the two curves, rounded up to the next decade. That is
the *same statistic* `judge_curve` compares against the curve pass budget. So the published bound
divided by that budget is the share of a verdict's tolerance that is spent on nothing but the
choice of solver — and a reader entitled to ask "how much of this tolerance is absorbing solver
noise?" can now be answered with a number instead of an assurance.

One class does not fit that sentence and is measured separately below. Two Gillespie ensembles of
the same model agree only up to Monte Carlo error, so the stochastic class publishes a count of
combined standard errors rather than a distance — dividing it by the curve budget would produce a
number about nothing. What it spends is the *resolution*: the smallest bias the comparison could
have seen, which on one of its three networks is wider than that class's own pass budget.

Read off the committed records, so it is a guard and not a paragraph: an engine upgrade that made
the two disagree more would move these numbers and fail here.
"""

from __future__ import annotations

import json

import pytest
from reprolith.mcp_server import milestone_certificate_dirs

#: The class default for a curve judged against a printed number: pass at 0.10, partial at 0.25.
_CURVE_PASS = 0.10

_SOURCES = milestone_certificate_dirs()


def _records() -> dict[str, dict]:
    """Every committed corroboration record, keyed by model class."""
    found = {}
    for model_class, directory in _SOURCES.items():
        path = directory.parent / "corroboration.json"
        if path.is_file():
            found[model_class] = json.loads(path.read_text(encoding="utf-8"))
    return found


def test_five_classes_carry_a_second_engine_and_one_does_not() -> None:
    """The absence is half the finding, so it is asserted rather than assumed.

    A test that only checked the classes with a record would keep passing if a class quietly lost
    its second engine, and the page that publishes this would keep saying nothing about it.

    This list is written down rather than derived, because a class acquiring or losing a second
    engine is a change a reader should be told about, not one a test should absorb — and it earned
    that the hard way. It used to name two classes without one, on the stated grounds that no
    installed implementation but this one answers their questions. That was true of a
    finite-difference reaction-diffusion solve and false of a Gillespie ensemble: libRoadRunner
    ships one, and it was already installed here as the ODE classes' second engine.
    """
    records = _records()
    assert set(records) == {
        "ode-pkpd", "kinetic", "constraint-based", "logical", "stochastic",
    }, sorted(records)
    assert set(_SOURCES) - set(records) == {"spatial"}


def test_the_engine_itself_spends_almost_none_of_the_curve_budget() -> None:
    """The result worth publishing: the tolerances are not absorbing solver disagreement.

    PK/PD's eighty claims are re-run at the dose each was certified at and agree to a published
    bound of 1e-06 — a *thousandth* of a percent of the curve pass budget. The kinetic class's six
    models agree to 1e-03, which is 1% of it: three orders looser than PK/PD and still two orders
    inside the budget. Neither is anywhere near the tolerance, so a numeric verdict is a statement
    about the model and not about COPASI.
    """
    worst = {
        model_class: max(float(row["distance_at_most"]) for row in record.values())
        for model_class, record in _records().items()
    }
    assert worst["ode-pkpd"] == pytest.approx(1e-06)
    assert worst["kinetic"] == pytest.approx(1e-03)
    # The constraint-based pair is not a curve comparison and is not judged against the curve
    # budget: it is the relative difference between two LP optima. All eight publish 1e-08, which
    # is the floor rather than a measurement — below it the digits are the machine's BLAS and not
    # the two implementations' agreement, measured at up to 4e-11 apart between two machines
    # running the same eight models. See `_LP_NOISE_FLOOR`.
    assert worst["constraint-based"] == pytest.approx(1e-08)

    shares = {name: bound / _CURVE_PASS for name, bound in worst.items()}
    assert shares["ode-pkpd"] < 1e-04       # a hundredth of a percent of the budget
    assert shares["kinetic"] == pytest.approx(0.01, rel=1e-6)  # one percent of it

    # And every single record, not only the worst: no committed result rests on one solver.
    for model_class, record in _records().items():
        for key, row in record.items():
            assert row["engine_independent"] is True, (model_class, key)
            if row.get("comparison") == "monte-carlo-agreement":
                # Not a curve distance and not comparable to one. Dividing a count of standard
                # errors by the curve budget gives 19, which would read as this class spending
                # nineteen times its whole tolerance on the solver — a number about nothing. What
                # this class spends is measured below, in the units it is actually in.
                continue
            assert float(row["distance_at_most"]) / _CURVE_PASS < 0.05, (model_class, key)


#: The scalar pass budget the stochastic class judges a reported mean against.
_SCALAR_PASS = 0.05


def test_the_ensemble_corroboration_is_weaker_than_the_verdict_it_stands_beside() -> None:
    """The one class where "the second engine agreed" is not a comfortable statement.

    Every class above agrees three to eight orders inside its budget, so a pass there needs no
    caveat. Two Gillespie ensembles cannot do that: they agree only up to Monte Carlo error, and
    what a pass is worth is the size of the bias it could have seen. On the Poisson-mean-10
    network three combined standard errors is 6.5% of the mean — *wider* than the 5% the same
    class's own scalar verdict passes at, so engine sensitivity is ruled out there only above a
    discrepancy larger than the one the verdict itself would catch.

    Asserted rather than written down, because the fix is not a tighter tolerance — it is more
    trajectories, and this is the number that would show them arriving.
    """
    record = _records()["stochastic"]
    resolutions = {key: float(row["resolves_bias_above"]) for key, row in record.items()}
    assert resolutions["immigration_death_10"] > _SCALAR_PASS
    assert resolutions["reversible_isomerization"] < _SCALAR_PASS
    for key, row in record.items():
        # The comparison is a count of standard errors against a criterion of three, so a row that
        # passes is at most three — and a row published at, say, 2.9 is one re-seed from flipping.
        assert 0.0 < float(row["distance_at_most"]) <= 3.0, key


#: Which two implementations each corroborated class was compared across. Named per class rather
#: than as one pair: the constraint-based class does not run a simulator at all, and a check that
#: demanded COPASI of it would either fail or have to be loosened into asking nothing.
#: Which two implementations each corroborated class was compared across. Named per class rather
#: than as one pair: the constraint-based class does not run a simulator at all, and the logical
#: class is compared two ways — CANA enumerates the small networks' attractors, and sympy's SAT
#: enumerates the large ones' fixed points, which is the question those certificates rest on. A
#: check that demanded COPASI of any of them would either fail or have to be loosened into asking
#: nothing.
_PAIRS = {
    "ode-pkpd": [["copasi", "roadrunner"]],
    "kinetic": [["copasi", "roadrunner"]],
    "constraint-based": [["cobrapy", "scipy-linprog"]],
    "logical": [["cana", "reprolith-logical"], ["reprolith-logical", "sympy-sat"]],
    "stochastic": [["reprolith-ssa", "roadrunner-gillespie"]],
}


def test_every_corroborated_run_names_the_two_engines_it_compared() -> None:
    """A record that does not say which engines agreed is not evidence that two of them did."""
    for model_class, record in _records().items():
        for key, row in record.items():
            assert sorted(row["engines"]) in _PAIRS[model_class], (model_class, key)


def test_a_discrete_agreement_is_not_published_as_a_distance() -> None:
    """An attractor set is the same object or it is not; 0e+00 is not a measurement of that.

    The logical class's rows carry `comparison: exact-match`, and both published surfaces read it
    — otherwise a discrete match prints as "engine-independent to 0e+00" and reads as the best
    agreement on the page rather than as a different kind of statement.
    """
    for key, row in _records()["logical"].items():
        assert row["comparison"] == "exact-match", key
        assert row["distance_at_most"] == 0.0, key
    # And the stochastic class's rows say a third thing, for a third reason: a count of standard
    # errors printed as `2e+00` beside the kinetic class's 1e-03 reads as a catastrophe.
    for key, row in _records()["stochastic"].items():
        assert row["comparison"] == "monte-carlo-agreement", key

    # And the classes compared by distance say nothing of the kind.
    for model_class in ("ode-pkpd", "kinetic", "constraint-based"):
        for key, row in _records()[model_class].items():
            assert "comparison" not in row, (model_class, key)
