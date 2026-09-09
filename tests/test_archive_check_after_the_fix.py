"""A fix that survives being acted on is the first line of the second run.

`archive-check` on an archive whose SED-ML only *reports* files one item, at the top: "the archive
states no published result … pass your claims file to `reprolith archive-check --claims` instead".
An author who does exactly that re-runs it and reads the identical headline — the instruction to do
the thing they have just done, above a check that used their file and compared fourteen results.

What is still true after they act is narrower, and it is the part worth saying: the results were
checked *here*, from a file the archive does not carry, so a stranger who downloads the archive
alone still has nothing to check the run against. What is no longer true is that they should go and
pass a claims file.

The archive under test is one Reprolith itself writes. `export` emits reports and never plots, on
purpose — SED-ML's way of saying "my paper published this" is a plot, and emitting one would
manufacture a published result per state variable — so this is the exact file the project's own
exporter produces, checked by the project's own checker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from reprolith.certify import Claim
from reprolith.presubmission import archive_report

_ROOT = Path(__file__).parent.parent
_ARCHIVE = _ROOT / "datasets" / "worked_examples" / "metformin_reconstruction.omex"


def _claims() -> tuple[Claim, ...]:
    return (
        Claim(
            claim_id="Cmax-plasma", quantity="plasma Cmax", species="mPlasmaVenous",
            metric="cmax", reported=6.1, source_location="Table 1",
        ),
    )


def _no_claim_item(report: dict) -> dict | None:
    return next((a for a in report["fix_list"] if a["kind"] == "claims"), None)


def _report(**kwargs) -> dict:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    return archive_report(_ARCHIVE, **kwargs)


def test_without_a_claims_file_the_item_asks_for_one() -> None:
    item = _no_claim_item(_report())
    if item is None:
        pytest.skip("this archive states a published result, so the item does not arise")
    assert "pass your claims file" in item["fix"]


def test_with_a_claims_file_it_stops_asking_for_the_claims_file() -> None:
    item = _no_claim_item(_report(claims=_claims()))
    if item is None:
        pytest.skip("this archive states a published result, so the item does not arise")
    assert "pass your claims file" not in item["fix"]
    assert "cannot be closed in the archive" in item["fix"]


def test_it_still_reports_what_a_stranger_downloading_the_archive_would_find() -> None:
    """It must not vanish: the archive genuinely carries no published result either way."""
    item = _no_claim_item(_report(claims=_claims()))
    if item is None:
        pytest.skip("this archive states a published result, so the item does not arise")
    assert "states no published result" in item["issue"]
    assert "1 result(s) you passed were checked against it here" in item["issue"]
