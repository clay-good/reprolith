"""A second engine for the logical class: CANA on the attractor sets, sympy's SAT on the large ones.

This class's certificates rested on one implementation — this one — while an independent library
that answers exactly the same question was already installed here to generate its committed
cross-validation references. The difference between those references and this is *when*: a
reference says the two tools agreed once, on the rules as they stood then; corroboration re-runs
both now, on the model each certificate is about, and publishes what the second one said
(roadmap #5).

Two comparisons, because the class asks two questions. CANA enumerates the small networks'
synchronous attractors; for the 44-to-60-node signalling models, where 2ⁿ enumeration is
impossible for either implementation, sympy's DPLL enumerates the fixed-point set that those
certificates actually rest on — and it shares no code with the z3 Reprolith solves them with.

Both are discrete: two enumerations of the same network return the same object or they do not.

Needs the ``sat`` extra (z3) and the ``corroborate`` extra (CANA, sympy); skips without them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("cana", reason="the optional 'corroborate' extra (CANA) is not installed")
pytest.importorskip("sympy", reason="the optional 'corroborate' extra (sympy) is not installed")
pytest.importorskip("z3", reason="the optional 'sat' extra (z3) is not installed")

from reprolith.corroboration import (  # noqa: E402
    corroborate_attractors,
    corroborate_fixed_points,
)

_LOG = Path(__file__).parent.parent / "datasets" / "logical"
_CROSS = _LOG / "cross_validation"
_MILESTONE = _LOG / "milestone"

_SMALL = json.loads((_CROSS / "reference.json").read_text(encoding="utf-8"))["models"]
_LARGE = json.loads((_CROSS / "scalable_fixed_points.json").read_text(encoding="utf-8"))["models"]


def _committed() -> dict:
    return json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))


def test_every_certified_network_is_covered_by_the_committed_record() -> None:
    """The population is the certificates, not the models that happened to be easy to re-run.

    A record covering the six small networks and silently omitting the three large ones would
    publish "logical: all engine-independent" over a class in which the hardest three — the ones a
    reader would most want a second opinion on — were never re-run.
    """
    certified = {p.stem for p in (_MILESTONE / "certificates").glob("*.json")}
    assert certified, "expected committed logical certificates"
    assert set(_committed()) == certified
    assert set(_SMALL) | set(_LARGE) == certified


@pytest.mark.parametrize("model_id", sorted(_SMALL))
def test_cana_reaches_the_same_attractor_signature(model_id: str) -> None:
    result = corroborate_attractors(_SMALL[model_id]["rules"])
    assert result.stable
    assert result.engines == ("reprolith-logical", "cana")
    assert result.comparison == "exact-match"
    assert "agree exactly" in result.summary()
    assert _committed()[model_id]["engine_independent"] is True


@pytest.mark.parametrize("model_id", sorted(_LARGE))
def test_an_independent_sat_solver_reaches_the_same_fixed_points(model_id: str) -> None:
    """The whole set of states, not their count — a count is satisfied by any network with as many.

    These are the models whose certificates are the class's strongest claim (60 nodes, 2⁶⁰ states)
    and the ones no enumeration could check.
    """
    result = corroborate_fixed_points(_LARGE[model_id]["rules"])
    assert result.stable
    assert result.engines == ("reprolith-logical", "sympy-sat")
    assert result.comparison == "exact-match"
    assert _committed()[model_id]["engine_independent"] is True


def test_a_disagreement_is_reported_rather_than_absorbed(monkeypatch) -> None:
    """The branch that has to work for an agreement to mean anything.

    Two correct implementations of the same enumeration do not disagree on these networks, which
    is the result — and it means the engine-sensitive path is never taken by any real input here.
    A branch no test reaches is a branch that can rot into always-agreeing, and this whole record
    would then be a record of nothing. So the second implementation's answer is replaced with a
    wrong one, and the comparison has to say so.
    """
    from reprolith import corroboration as module

    monkeypatch.setattr(
        module, "_cana_signature", lambda rules: ((99, (1,) * 99), "1.0.0-fabricated")
    )
    result = corroborate_attractors(_SMALL["repressilator"]["rules"])
    assert not result.stable
    assert "do not agree" in result.summary()
    assert result.record()["engine_independent"] is False


def test_the_record_names_the_builds_it_was_measured_on() -> None:
    for accession, row in _committed().items():
        assert row["comparison"] == "exact-match", accession
        assert all(version for version in row["engine_versions"]), accession
        # Reprolith's own side names the code that ran, not a package version that never moves —
        # the same thing a certificate's freshness check reads.
        assert "rev " in row["engine_versions"][0], accession


def test_a_partial_model_is_refused_rather_than_compared() -> None:
    """A satisfiability search may leave a variable undecided; that answer is a set, not a state.

    Compared against a complete state it is simply unequal, and the record would then say a
    model's certified steady states are solver-dependent — a claim about the network, made on
    evidence about the shape of one answer. Exercised directly, because the three committed
    networks never produce one.
    """
    import sympy
    from reprolith.corroboration import _complete_assignment

    rules = {"a": "b", "b": "a", "c": "!c"}
    complete = {sympy.Symbol("a"): True, sympy.Symbol("b"): True, sympy.Symbol("c"): False}
    assert _complete_assignment(complete, rules) == frozenset(
        {("a", 1), ("b", 1), ("c", 0)}
    )
    with pytest.raises(ValueError, match="undecided"):
        _complete_assignment({sympy.Symbol("a"): True}, rules)


def test_the_pin_names_the_path_that_actually_ran() -> None:
    """Below the enumeration bound no SAT solver is called, and the record must not name one.

    `solver_pin_for` exists because a caller choosing the pin publishes one that contradicts its
    own protocol; this comparison reintroduced that choice and now reads the network's size.
    """
    small = corroborate_fixed_points(_SMALL["repressilator"]["rules"])
    large = corroborate_fixed_points(_LARGE["leukemia"]["rules"])
    assert small.stable and large.stable
    # A 3-node network is walked state by state and a 60-node one is solved by z3; one build
    # string cannot be right for both, and the package version — which has never moved — is right
    # for neither.
    assert "enumeration" in small.versions[0]
    assert "sat-fixed-points" in large.versions[0]
    assert "rev " in small.versions[0] and "rev " in large.versions[0]
