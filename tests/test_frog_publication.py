"""The FROG fingerprint this class was asked to generate, and the one it publishes.

FROG — flux optimum, reaction variability, objective, gene and reaction deletion — is the
constraint-based field's own portable reproducibility artifact. The `constraint-based-class` spec
asks this class to generate one and to make a verdict the comparison of two where a second is
available. `frog_fingerprint` has computed one since the class was written, and nothing published
or compared it: the whole requirement was carried by unit tests.

A second one *is* available. COBRApy computes every component from a different reader and a
different LP backend, so the committed record is a cross-implementation comparison rather than this
solver checking itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_RECORD = (
    Path(__file__).parent.parent
    / "datasets" / "constraint_based" / "milestone" / "frog" / "e_coli_core.json"
)


def test_the_committed_fingerprint_comparison_covers_every_component() -> None:
    """423 of them on this model: the objective, both variability bounds and the deletion
    objective for each of 95 reactions, and the deletion objective for each of 137 genes. A
    comparison that quietly covered the objective alone would publish as a fingerprint match."""
    record = json.loads(_RECORD.read_text(encoding="utf-8"))
    assert record["reactions"] == 95
    assert record["genes"] == 137
    assert record["components_compared"] == 1 + 3 * record["reactions"] + record["genes"]
    assert record["engines"] == ["scipy-linprog", "cobrapy"]
    assert all(record["engine_versions"])


def test_every_component_group_agrees_by_the_same_rule_a_verdict_would_use() -> None:
    """`compare_frog` decides it — the same function a curated fingerprint would be judged
    against — rather than a second comparison written beside it.

    Reaching for it found something a hand-rolled comparison had missed: COBRApy reports a lethal
    knockout as NaN with an infeasible status where this package reports 0.0, and `abs(a - b)` on a
    NaN is a NaN that never becomes the worst difference. So four components were not compared at
    all while the record said 423 agreed. The convention is translated explicitly now, counted in
    the record, and a NaN whose status is *not* infeasible raises instead."""
    record = json.loads(_RECORD.read_text(encoding="utf-8"))
    assert record["agrees"] is True
    for group in ("objective", "variability", "deletion", "gene_deletion"):
        assert record[f"{group}_agrees"] is True, group
    assert record["disagreements"] == []
    # Said out loud: the two sides did not literally return the same value for these four.
    assert record["infeasible_deletions_translated"] == 4


def test_the_two_implementations_agree_across_the_whole_fingerprint() -> None:
    """Measured against the model's own scale — its optimal objective — and not against each
    component's magnitude, which is the denominator trap this repository keeps meeting: the worst
    component here is a flux bound both sides call numerically zero, 5.6e-14 against 3.0e-12,
    whose *relative* difference is 3e-03 and means nothing."""
    record = json.loads(_RECORD.read_text(encoding="utf-8"))
    assert record["worst_difference_of_objective"] < 1e-9, record["worst_difference_at"]
    assert record["worst_difference_at"], "the worst component is named, not just counted"


def test_the_record_is_what_the_two_implementations_produce_today() -> None:
    """Live, because a test that reads the artifact does not guard the code that writes it."""
    pytest.importorskip("cobra", reason="the 'corroborate' extra is not installed")
    pytest.importorskip("scipy", reason="the 'fba' extra is not installed")
    from reprolith.corroboration import frog_agreement

    sbml = (
        Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
    ).read_text(encoding="utf-8")
    fresh = frog_agreement(sbml)
    committed = json.loads(_RECORD.read_text(encoding="utf-8"))
    for field in ("reactions", "genes", "components_compared", "engines", "agrees",
                  "infeasible_deletions_translated"):
        assert fresh[field] == committed[field], field
    # Not the last digits: an LP optimum's last places move with the BLAS underneath it, which
    # this repository has measured across machines before. The claim is the agreement's size.
    assert fresh["worst_difference_of_objective"] < 1e-9


def test_a_lethal_knockout_is_translated_and_an_unanswered_one_is_refused() -> None:
    """The two implementations agree about a lethal knockout and say it differently: `0.0` here,
    NaN with an infeasible status there. That is translated explicitly and counted. A NaN whose
    status is *not* infeasible is the other implementation declining to answer, and reading it as
    zero growth would publish an agreement about a number nobody computed."""
    from reprolith.corroboration import _deletion_growths

    growths, translated = _deletion_growths(
        {"ids": [{"A"}, {"B"}], "growth": [0.5, float("nan")],
         "status": ["optimal", "infeasible"]},
        "reaction",
    )
    assert growths == {"A": 0.5, "B": 0.0}
    assert translated == ["B"]

    with pytest.raises(ValueError, match="declining to answer"):
        _deletion_growths(
            {"ids": [{"C"}], "growth": [float("nan")], "status": ["numeric_error"]}, "gene"
        )


def test_two_fingerprints_of_different_models_are_refused() -> None:
    """Comparing the part that happens to line up would publish a fingerprint match for two
    different models."""
    from reprolith.corroboration import _require_same_model

    _require_same_model(
        reaction_ids=("R_PFK",), gene_ids=("G_b1723",),
        theirs_reactions={"PFK"}, theirs_genes={"b1723"},
    )
    with pytest.raises(ValueError, match="appear in only one of them"):
        _require_same_model(
            reaction_ids=("R_PFK", "R_ONLY_MINE"), gene_ids=(),
            theirs_reactions={"PFK"}, theirs_genes=set(),
        )


def test_a_fingerprint_of_a_different_model_is_refused_rather_than_part_compared() -> None:
    """Identifiers that appear in only one fingerprint are a structural disagreement about which
    model is being described, and comparing the part that happens to line up would publish a match
    for two different models. COBRApy strips the SBML `R_`/`G_` prefixes this package keeps, so
    the alignment has to know that — without it, every reaction reads as present in only one."""
    pytest.importorskip("cobra", reason="the 'corroborate' extra is not installed")
    from reprolith.corroboration import _bare

    assert _bare("R_PFK") == "PFK"
    assert _bare("G_b1723") == "b1723"
    assert _bare("PFK") == "PFK"
