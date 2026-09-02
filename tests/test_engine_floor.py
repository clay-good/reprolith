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


def test_three_classes_carry_a_second_engine_and_three_do_not() -> None:
    """The absence is half the finding, so it is asserted rather than assumed.

    A test that only checked the classes with a record would keep passing if a class quietly lost
    its second engine, and the page that publishes this would keep saying nothing about it.

    The three without one are the three Reprolith solves itself where no widely-installed
    independent implementation answers the same question. That is why they are the ones left, and
    why this list is written down rather than derived: a class acquiring or losing a second engine
    is a change a reader should be told about, not one a test should absorb.
    """
    records = _records()
    assert set(records) == {"ode-pkpd", "kinetic", "constraint-based"}, sorted(records)
    assert set(_SOURCES) - set(records) == {"logical", "spatial", "stochastic"}


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
    # budget: it is the relative difference between two LP optima, and the widest of the eight is
    # 1e-10 — four orders inside even PK/PD's.
    assert worst["constraint-based"] == pytest.approx(1e-10)

    shares = {name: bound / _CURVE_PASS for name, bound in worst.items()}
    assert shares["ode-pkpd"] < 1e-04       # a hundredth of a percent of the budget
    assert shares["kinetic"] == pytest.approx(0.01, rel=1e-6)  # one percent of it

    # And every single record, not only the worst: no committed result rests on one solver.
    for model_class, record in _records().items():
        for key, row in record.items():
            assert row["engine_independent"] is True, (model_class, key)
            assert float(row["distance_at_most"]) / _CURVE_PASS < 0.05, (model_class, key)


#: Which two implementations each corroborated class was compared across. Named per class rather
#: than as one pair: the constraint-based class does not run a simulator at all, and a check that
#: demanded COPASI of it would either fail or have to be loosened into asking nothing.
_PAIRS = {
    "ode-pkpd": ["copasi", "roadrunner"],
    "kinetic": ["copasi", "roadrunner"],
    "constraint-based": ["cobrapy", "scipy-linprog"],
}


def test_every_corroborated_run_names_the_two_engines_it_compared() -> None:
    """A record that does not say which engines agreed is not evidence that two of them did."""
    for model_class, record in _records().items():
        for key, row in record.items():
            assert sorted(row["engines"]) == _PAIRS[model_class], (model_class, key)
