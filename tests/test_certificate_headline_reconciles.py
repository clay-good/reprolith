"""A headline short of a clean pass, over a count line in which nothing fell short.

Six of the certificates this repository publishes open like this:

    OVERALL: partially-reproduced
      claims by verdict: reproduced=1, partial=0, failed=0, not-evaluable=0

A reader's first check of the headline is the line under it, and that line says every claim
reproduced. The reconciliation is real and one line further down — `assumption-qualified claims:
...` — and it never said it *was* the reconciliation, so the connection was left to be inferred. The
selection line in the same renderer already had this problem and already solved it the same way:
state it beside the counts rather than leave it to a section further down the page.

Derived, never asserted: every claim reproduced, at least one resting on an assumption Reprolith
supplied, and a headline short of `reproduced`. A certificate with a genuine partial or a failure
says nothing extra, because there the counts explain themselves.
"""

from __future__ import annotations

from pathlib import Path

from reprolith.render import qualification_is_the_whole_downgrade

_ROOT = Path(__file__).resolve().parents[1]

_CLEAN_PASS = "the only reason this is not a clean pass"


def _committed() -> list[Path]:
    return sorted(_ROOT.joinpath("datasets").rglob("**/certificate*.txt")) + sorted(
        _ROOT.joinpath("datasets").rglob("**/certificates/*.txt")
    )


def test_every_committed_certificate_that_needs_the_reconciliation_carries_it() -> None:
    """Read from the artifacts, because a reader opens those and not the function that writes them.

    A committed certificate whose headline is not `reproduced` while its counts show nothing but
    reproduced claims is exactly the artifact this line exists for.
    """
    checked = 0
    for path in _committed():
        text = path.read_text(encoding="utf-8")
        if "OVERALL: reproduced" in text:
            assert _CLEAN_PASS not in text
            continue
        counts = next(
            (line for line in text.splitlines() if "claims by verdict:" in line), ""
        )
        if not counts or not all(
            f"{verdict}=0" in counts for verdict in ("partial", "failed", "not-evaluable")
        ):
            continue
        checked += 1
        assert _CLEAN_PASS in text, f"{path} leaves its headline unreconciled"
    # The corpus does contain such certificates; a version of this test that checked nothing would
    # pass just as quietly.
    assert checked >= 6


def test_a_genuine_partial_says_nothing_extra() -> None:
    """The counts explain themselves there, and a sentence claiming the assumptions are "the only
    reason" would be false the moment a claim actually falls short."""
    from reprolith import Assumption, PaperIdentity
    from reprolith.certificate import build_certificate
    from reprolith.enums import Verdict
    from reprolith.model import ClaimAssessment, EnginePin

    def _assessment(verdict: Verdict, qualified: bool) -> ClaimAssessment:
        return ClaimAssessment(
            claim_id=f"c-{verdict.value}-{qualified}", quantity="q", verdict=verdict,
            source_location="Table 1", discrepancy="d", assumption_qualified=qualified,
            # A miss this certificate asserts has to say what missed — the builder refuses one
            # that does not, which is the invariant this fixture has to satisfy rather than route
            # around.
            root_cause=None if verdict is Verdict.REPRODUCED else "the reconstruction under-predicts",
        )

    pin = EnginePin(engine="e", version="1", algorithm="a")
    assumption = Assumption(
        id="a1", description="d", chosen="v", basis="b", load_bearing=True,
    )
    qualified_only = build_certificate(
        paper=PaperIdentity(title="t"), engine_pin=pin,
        assessments=[_assessment(Verdict.REPRODUCED, True)], assumptions=[assumption],
    )
    assert qualification_is_the_whole_downgrade(qualified_only)

    with_a_real_partial = build_certificate(
        paper=PaperIdentity(title="t"), engine_pin=pin,
        assessments=[_assessment(Verdict.REPRODUCED, True), _assessment(Verdict.PARTIAL, False)],
        assumptions=[assumption],
    )
    assert not qualification_is_the_whole_downgrade(with_a_real_partial)


def test_the_page_says_it_too() -> None:
    """The registry card is the one place a reader sees a verdict with no way to ask the
    certificate a follow-up question, so the two renderings must not explain one headline
    differently."""
    page = (_ROOT / "datasets" / "registry.html").read_text(encoding="utf-8")
    assert "short of a clean pass only for an assumption Reprolith supplied" in page
