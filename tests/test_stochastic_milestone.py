"""The committed stochastic milestone artifact stays consistent (spec: stochastic-class).

Dependency-free guard on `scripts/run_stochastic_milestone.py`: if the committed agreement report,
certificates, or catalog drift from a full-agreement blind run over the analytically-grounded
systems, this fails and the artifact must be regenerated. Reading JSON needs no extras.
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "stochastic" / "milestone"
#: The three summary-statistic entries and the first-passage one. Every certificate in this class
#: used to be `partially-reproduced` for the same reason — the ensemble was Reprolith's choice, so
#: no verdict here was unqualified. Every one of them is now a clean `reproduced`: the ensembles
#: were bought up to the size at which a draw's own error bar is within a tenth of the band the
#: claim is judged in, where it stops being a choice the verdict rests on.
_MEANS = {"immigration_death_10", "immigration_death_4", "reversible_isomerization"}
_EXTINCTION = {"death_extinction_time"}
#: The noise entry: the Fano factor and the coefficient of variation of the same Poisson process
#: the means above are read from, which are the quantities a stochastic model exists to describe.
_NOISE = {"immigration_death_noise"}
_EXPECTED = _MEANS | _EXTINCTION | _NOISE


def test_agreement_report_shows_a_blind_full_agreement() -> None:
    report = json.loads((_MILESTONE / "agreement_report.json").read_text(encoding="utf-8"))
    assert report["total"] == len(_EXPECTED)
    assert report["agreements"] == report["total"]
    assert report["agreement_rate"] == 1.0
    for entry in report["per_entry"]:
        # The closed form says the model reproduces these numbers, and the run says so too. The
        # expected label used to read `partially-reproduced`, which was a statement about how this
        # engine behaved rather than about the mathematics it cites as its source.
        assert entry["expected"] == "reproduced"
        assert entry["actual"] == "reproduced"
        assert entry["agree"] is True


def test_every_certificate_is_an_unqualified_stochastic_reproduction() -> None:
    """Clean passes, and the protocol line says why each one carries no sampling assumption."""
    for key in _EXPECTED:
        content = json.loads((_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8"))
        assert content["overall"] == "reproduced"
        assert content["scope"]["machine"] == "reproducible-not-correct-not-clinical"
        assert content["assumptions"] == []
        claim = content["assessments"][0]
        assert claim["verdict"] == "reproduced" and claim["assumption_qualified"] is False
        assert claim["method"] == "scalar-relative-error"
        assert "not a choice the verdict rests on" in claim["protocol"]


def test_the_catalog_recorded_every_entry_as_a_certified_stochastic_model() -> None:
    catalog = json.loads((_MILESTONE / "catalog.json").read_text(encoding="utf-8"))
    entries = catalog["entries"]
    assert len(entries) == len(_EXPECTED)
    for entry in entries:
        assert entry["model_class"] == "stochastic"
        assert entry["state"] == "certified"


def test_the_first_passage_entry_certifies_a_mean_extinction_time() -> None:
    """The class's fourth entry and its first non-summary-statistic one: a pure death process
    leaves the mean time to extinction at `H(n0)/k`, which is closed-form ground truth needing no
    external tool. `time_to_extinction` had been implemented, with its censoring semantics worked
    out, and unreachable from any certificate."""
    (key,) = _EXTINCTION
    content = json.loads((_MILESTONE / "certificates" / f"{key}.json").read_text(encoding="utf-8"))
    (assessment,) = content["assessments"]
    assert assessment["quantity"] == "mean time to extinction"
    assert assessment["verdict"] == "reproduced"
    # The cap each trajectory ran under is part of the protocol, because it decides what the
    # number means: a run that reaches it observed no extinction at all.
    assert "capped at t=" in assessment["protocol"]
    assert "the mean's standard error is" in assessment["protocol"]
    # And no second engine stands behind it, which the corroboration surface reports rather than
    # counting it among the corroborated three.
    corroboration = json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))
    assert key not in corroboration
