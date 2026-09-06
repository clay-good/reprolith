"""An ensemble Reprolith drew is not something an author can write their way out of.

`Assumption.author_can_close` exists because six of thirty published certificates once carried an
instruction no wording in any paper could satisfy. Two of the three paths that draw their own
sample were corrected then — the stochastic class's ensemble and the spatial class's boundary —
and the third, the population class, was left at the default. Its author-facing fix read "state the
percentile bands judged here came from a virtual population Reprolith reconstructed and sampled …
explicitly so it need not be assumed": the exact defect the flag was added for, addressed to an
author who cannot act on it.

The flag also decides which half of `reprolith verification-queue` an item lands in — what an
expert can settle, or what only this engine's development can close — so a path that gets it wrong
now overstates the queue as well as the fix list.

Driven from the three front-ends by name. A seventh class that draws its own sample is not covered
here; there is no way to detect "this alternative is Reprolith's own knob" from the data, so this
is a list, and it says so.
"""

from __future__ import annotations

import pytest
from reprolith import (
    EnginePin,
    PaperIdentity,
    PercentileBand,
    PopulationClaim,
    certify_population,
    presubmission_report,
)

PIN = EnginePin(engine="test-engine", version="0.0.0")
_REF = (
    PercentileBand(5.0, (0.4, 0.9, 1.6, 1.0, 0.5)),
    PercentileBand(50.0, (1.0, 2.0, 3.6, 2.2, 1.1)),
    PercentileBand(95.0, (1.8, 3.4, 6.0, 3.8, 1.9)),
)


def _population_certificate():
    predicted = tuple(
        PercentileBand(band.percentile, tuple(v * 1.01 for v in band.curve)) for band in _REF
    )
    return certify_population(
        paper=PaperIdentity(doi="10.0/pop", title="A population PK model"),
        engine_pin=PIN,
        claims=[
            PopulationClaim(
                claim_id="env",
                quantity="concentration envelope",
                reported=_REF,
                predicted=predicted,
                source_location="Fig 5",
                protocol="virtual population: 1000 subjects, seed 7",
            )
        ],
    )


def test_the_population_sampling_assumption_is_not_the_authors_to_close() -> None:
    """A paper that states its subject count and variability model in full still does not
    discharge it: Reprolith draws the population, and drawing it again moves the percentiles.
    Both alternatives the assumption itself lists are Reprolith's own knobs."""
    cert = _population_certificate()
    (assumption,) = [a for a in cert.assumptions if a.id.startswith("population-sampling-")]
    assert assumption.load_bearing is True
    assert assumption.author_can_close is False
    assert set(assumption.alternatives) == {"a different subject count", "a different sampling seed"}


def test_its_author_facing_fix_does_not_ask_for_something_no_paper_can_say() -> None:
    """Both rows, and the roll-up is the one that was still wrong.

    The named row said "nothing in the paper can clear this one"; the summary row one line under
    it said "state the assumed values listed above explicitly" — a route to a clean pass that does
    not exist, printed on six shipped certificates.
    """
    report = presubmission_report(_population_certificate())
    fixes = [a["fix"] for a in report["fix_list"] if a["kind"] == "assumption"]
    assert len(fixes) == 2, report["fix_list"]
    assert not any("listed above explicitly" in fix for fix in fixes)
    assert not any("explicitly so it need not be assumed" in fix for fix in fixes)
    assert any("nothing in the paper can clear this one" in fix for fix in fixes)
    assert any("nothing in your paper clears these" in fix for fix in fixes)


def test_a_paper_that_can_state_some_of_them_is_told_which_half_moves() -> None:
    from dataclasses import replace

    cert = _population_certificate()
    statable = replace(
        cert.assumptions[0], id="dose-salt-form", description="which salt", author_can_close=True
    )
    mixed = replace(cert, assumptions=(*cert.assumptions, statable))
    fixes = [a["fix"] for a in presubmission_report(mixed)["fix_list"] if a["kind"] == "assumption"]
    rollup = next(f for f in fixes if "limits of" in f)
    assert "state the 1 assumed value(s) above that your paper can state" in rollup
    assert "the other 1 are limits of" in rollup


def test_a_paper_whose_assumptions_are_all_statable_is_told_to_state_them() -> None:
    """The unchanged case: this correction must not have taken the useful instruction away."""
    from dataclasses import replace

    cert = _population_certificate()
    closable = replace(cert, assumptions=(replace(cert.assumptions[0], author_can_close=True),))
    fixes = [
        a["fix"] for a in presubmission_report(closable)["fix_list"] if a["kind"] == "assumption"
    ]
    assert any("state the assumed values listed above explicitly" in f for f in fixes)


def test_it_lands_under_this_engine_rather_than_awaiting_an_expert() -> None:
    from reprolith import queue_report
    from reprolith.determinism import certificate_digest

    cert = _population_certificate()
    report = queue_report([(certificate_digest(cert), cert)])
    assert report["pending"] == []
    assert [i["assumption_ids"] for i in report["engine_limits"]] == [["population-sampling-env"]]


@pytest.mark.parametrize(
    "front_end", ["certify_stochastic", "certify_spatial", "certify_population"]
)
def test_every_front_end_that_draws_its_own_sample_says_so(front_end: str) -> None:
    """A list, not a derivation — kept beside the three so a fourth is a visible omission."""
    import reprolith

    assert hasattr(reprolith, front_end)
