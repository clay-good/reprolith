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
    for field in ("reactions", "genes", "components_compared", "engines"):
        assert fresh[field] == committed[field], field
    # Not the last digits: an LP optimum's last places move with the BLAS underneath it, which
    # this repository has measured across machines before. The claim is the agreement's size.
    assert fresh["worst_difference_of_objective"] < 1e-9


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
