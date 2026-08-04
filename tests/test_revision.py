"""Tracked dossier revision (bootstrap task 2.4)."""

from __future__ import annotations

import pytest
from reprolith import (
    Dossier,
    DossierHistory,
    Parameter,
    dossier_digest,
    revise,
)


def _dossier(cl_value: float) -> Dossier:
    return Dossier(
        entry="10.1/x",
        parameters=(Parameter(name="CL", value=cl_value, unit="L/h", source_location="Table 1"),),
    )


def test_correction_is_applied_and_original_remains_retrievable() -> None:
    original = _dossier(5.0)  # mis-extracted clearance
    corrected = _dossier(5.2)  # reviewer fixes it

    history = DossierHistory()
    original_digest = history.record_original(original)

    revision = revise(original, corrected, corrector="curator@lab", rationale="Table 1 reads 5.2, not 5.0",
                      at="2026-08-03T00:00:00Z")
    history.record_revision(revision)

    # The correction is applied and tracked with who/why/when.
    assert revision.dossier.parameters[0].value == 5.2
    assert revision.corrector == "curator@lab"
    assert revision.rationale == "Table 1 reads 5.2, not 5.0"
    assert revision.supersedes == original_digest

    # The original extraction remains retrievable, unchanged.
    recovered = history.get(original_digest)
    assert recovered is original
    assert recovered.parameters[0].value == 5.0


def test_revision_requires_a_rationale() -> None:
    with pytest.raises(ValueError):
        revise(_dossier(5.0), _dossier(5.2), corrector="c", rationale="  ", at="t")


def test_history_chain_walks_newest_first() -> None:
    v1 = _dossier(5.0)
    v2 = _dossier(5.2)
    v3 = _dossier(5.25)

    history = DossierHistory()
    history.record_original(v1)
    history.record_revision(revise(v1, v2, corrector="c", rationale="fix 1", at="t1"))
    history.record_revision(revise(v2, v3, corrector="c", rationale="fix 2", at="t2"))

    assert history.chain(v3) == (v3, v2, v1)


def test_digest_is_stable_for_equal_content() -> None:
    assert dossier_digest(_dossier(5.0)) == dossier_digest(_dossier(5.0))
    assert dossier_digest(_dossier(5.0)) != dossier_digest(_dossier(5.2))
