"""A budgeted certification of a real paper, from the dossier's footprints to the certificate.

The pieces are each tested on their own — ``test_claim_selection.py`` for what a paper's claims
carry into the objective, ``test_budgeted_certificate.py`` for what a certificate must record —
and this is the walk that joins them on a published model: the dossier's footprints choose three
of fourteen claims, the engine runs exactly those three, and the certificate says which eleven it
did not attempt. Nothing is hand-written in between.

The subject is chosen for what it costs Reprolith. BIOMD0000001027 is the only entry in this
corpus whose certificate reads an unqualified ``reproduced`` — fourteen claims, all clean. Under a
budget of three it stops being one, which is the whole point of the qualification rule: three
passes out of fourteen claims is a weaker result than fourteen, and the word has to say so.

Needs the optional ``engine`` extra; skips without it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

from reprolith import (  # noqa: E402
    Claim,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    RunMetadata,
    Verdict,
    certificate_from_content,
    certify_model,
    claim_selection_pool,
    dossier_from_dict,
    plan_under_budget,
    render_human,
    select_greedily,
    select_jointly,
)

_ROOT = Path(__file__).resolve().parent.parent
_DATASETS = _ROOT / "datasets"
_ENTRY = "BIOMD0000001027"
_BUDGET = 3.0
_PIN = EnginePin(engine="copasi", version="4.46", algorithm="deterministic-lsoda")
_RUN = RunMetadata(created_at="2026-09-02T00:00:00Z", actor="tests", tool_version="0")


def _entry() -> dict:
    return json.loads((_DATASETS / "pkpd_claims.json").read_text(encoding="utf-8"))["entries"][
        _ENTRY
    ]


def _budgeted_certificate():
    entry = _entry()
    dossier = dossier_from_dict(
        json.loads((_DATASETS / "milestone" / "dossiers" / f"{_ENTRY}.json").read_text("utf-8"))
    )
    chosen, record = plan_under_budget(
        [Claim.from_record(claim) for claim in entry["claims"]],
        select_jointly(claim_selection_pool(dossier), budget=_BUDGET),
    )
    return chosen, record, certify_model(
        (_DATASETS / entry["model_file"]).read_text(encoding="utf-8"),
        paper=PaperIdentity(**entry["paper"]),
        engine_pin=_PIN,
        claims=chosen,
        selection=record,
        duration=entry["duration"],
        steps=entry["steps"],
    )


def test_a_budget_of_three_certifies_three_of_fourteen_and_names_the_eleven() -> None:
    chosen, record, cert = _budgeted_certificate()

    assert len(chosen) == 3
    assert len(cert.assessments) == 3
    assert all(a.verdict is Verdict.REPRODUCED for a in cert.assessments)

    # The eleven are named, and they are exactly the complement of what ran — not a count, not a
    # sample, and not a claim the certificate quietly forgot.
    attempted = {a.claim_id for a in cert.assessments}
    unattempted = {claim.claim_id for claim in record.unattempted}
    assert len(unattempted) == 11
    assert attempted | unattempted == {claim["claim_id"] for claim in _entry()["claims"]}
    assert not attempted & unattempted


def test_the_corpus_one_clean_pass_stops_being_one_under_a_budget() -> None:
    _, _, cert = _budgeted_certificate()
    published = json.loads(
        (_DATASETS / "milestone" / "certificates" / f"{_ENTRY}.json").read_text("utf-8")
    )
    assert published["overall"] == OverallVerdict.REPRODUCED.value  # all fourteen, unqualified
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED  # three of fourteen, qualified

    text = render_human(cert, _RUN)
    assert "claims: 14 in the paper, 3 attempted, 11 left unattempted under a budget" in text
    assert "NOT ATTEMPTED (chosen against by a budget, not judged)" in text


def test_the_budgeted_certificate_survives_being_written_down() -> None:
    # The verdict is re-derived on load, and it only follows from the evidence if the selection
    # came back with it: a stored budgeted certificate whose record was dropped is refused.
    _, _, cert = _budgeted_certificate()
    reloaded = certificate_from_content(json.loads(json.dumps(cert.content())))
    assert reloaded.content() == cert.content()
    assert reloaded.overall is OverallVerdict.PARTIALLY_REPRODUCED


def test_the_selection_guide_shows_what_a_budgeted_certificate_actually_prints() -> None:
    """The doc's second worked example is this run, and prose cannot keep it true.

    Its sibling in ``test_documented_commands.py`` pins the *plan*'s numbers the same way. A
    footprint depth or one more curated claim would change both silently — and here the lines at
    stake are the ones a reader takes as the certificate's own account of what it skipped.
    """
    _, record, cert = _budgeted_certificate()
    page = (_ROOT / "docs" / "claim-selection.md").read_text(encoding="utf-8")

    for line in render_human(cert, _RUN).splitlines():
        stripped = line.strip()
        if stripped.startswith(("OVERALL:", "claims by verdict:", "claims: 14", "budget 3,")):
            assert stripped in page, f"docs/claim-selection.md does not show: {stripped}"

    # And the comparison the section rests on: the set beat the ranking, by these numbers.
    dossier = dossier_from_dict(
        json.loads((_DATASETS / "milestone" / "dossiers" / f"{_ENTRY}.json").read_text("utf-8"))
    )
    pool = claim_selection_pool(dossier)
    joint = select_jointly(pool, budget=_BUDGET)
    greedy = select_greedily(pool, budget=_BUDGET)
    assert f"score {joint.score:.3f}, witnessing {len(joint.covered)} model elements" in page
    assert f"({greedy.score:.3f}, {len(greedy.covered)} elements)" in page
    assert record.objective.endswith("(exact)")
