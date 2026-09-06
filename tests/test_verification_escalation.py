"""Opening a queue item for every load-bearing value a standing certificate rests on.

The ``autonomous-build-loop`` spec says the loop escalates load-bearing uncertainty rather than
committing it silently, and its own "what carries each requirement today" section said nothing did:
the queue's shapes existed, ``Assumption.verification_item`` existed, and four published
certificates even cited an item id — ``verify:time-unit-of-the-Zake2021-deposits`` — that pointed
at nothing anybody could open. These tests hold the derivation to what makes it worth having: it
misses no load-bearing assumption, it changes no verdict, and it merges by the question rather than
by whichever claim the assumption happened to hang off.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    Assumption,
    ClaimAssessment,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    build_certificate,
    queue_from_certificates,
    queue_report,
)
from reprolith.determinism import certificate_digest
from reprolith.mcp_server import load_repository, milestone_certificate_dirs
from reprolith.persistence import certificate_from_content

PIN = EnginePin(engine="copasi", version="4.46")


def _assumption(**kw):
    base = dict(id="a", description="d", chosen="c", basis="b", load_bearing=True)
    base.update(kw)
    return Assumption(**base)


def _cert(*assumptions, title="t", verdict=Verdict.REPRODUCED):
    return build_certificate(
        paper=PaperIdentity(title=title),
        engine_pin=PIN,
        assessments=[
            ClaimAssessment(
                claim_id="c1", quantity="AUC", verdict=verdict, source_location="T1",
                assumption_qualified=bool(assumptions),
            )
        ],
        assumptions=list(assumptions),
    )


def _pairs(*certs):
    return [(certificate_digest(c), c) for c in certs]


# --- what it must not miss ----------------------------------------------------------------


def test_every_load_bearing_assumption_gets_an_item() -> None:
    cert = _cert(_assumption(id="one"), _assumption(id="two", description="other"))
    queue, _, _ = queue_from_certificates(_pairs(cert))
    assert len(queue) == 2


def test_an_assumption_that_is_neither_load_bearing_nor_named_is_not_queued() -> None:
    # The queue is for values that plausibly change an outcome. Filling it with the rest would
    # bury the two that matter under the thirty that do not.
    cert = _cert(_assumption(id="minor", load_bearing=False))
    queue, _, _ = queue_from_certificates(_pairs(cert))
    assert len(queue) == 0


def test_an_assumption_the_certificate_says_is_queued_is_queued() -> None:
    """`derive_overall` withholds a clean pass for a `verification_item` whether or not the
    assumption is flagged load-bearing, and the gap report names it either way. This loop tested
    only `load_bearing`, so the one assumption whose certificate says in so many words that it is
    under review was the one thing the queue left out.
    """
    cert = _cert(_assumption(id="minor", load_bearing=False, verification_item="verify:named"))
    report = queue_report(_pairs(cert))
    assert [i["id"] for i in report["pending"]] == ["verify:named"]


def test_no_committed_certificate_cites_an_item_the_queue_cannot_open() -> None:
    """The defect that started this: a citation to a queue item nobody built.

    Read off the committed certificates rather than a fixture, so a future certificate that names
    an item id fails here unless the derivation actually produces it.
    """
    cited, queue_ids = set(), set()
    for directory in milestone_certificate_dirs().values():
        for path in sorted(Path(directory).glob("*.json")):
            cert = certificate_from_content(json.loads(path.read_text(encoding="utf-8")))
            for assumption in cert.assumptions:
                if assumption.verification_item:
                    cited.add(assumption.verification_item)
            queue, _, _ = queue_from_certificates(_pairs(cert))
            queue_ids.update(item.id for item in queue.pending())
    assert cited, "no committed certificate names a verification item; this test guards nothing"
    assert cited <= queue_ids, sorted(cited - queue_ids)


# --- how it merges ------------------------------------------------------------------------


def test_one_question_asked_by_three_claims_is_one_item_with_three_dependents() -> None:
    """The spatial class's boundary condition, which is one limitation of one solver.

    Its assumption id names the claim it hangs off — ``spatial-boundary-diffusion_D1-profile`` and
    two siblings — under four fields that are character-for-character identical. Keyed by
    assumption id that is three items an expert answers three times.
    """
    certs = [
        _cert(_assumption(id=f"spatial-boundary-{n}-profile"), title=f"paper {n}")
        for n in ("D1", "D2", "Dhalf")
    ]
    report = queue_report(_pairs(*certs))
    assert report["pending_count"] == 1
    assert report["pending"][0]["impact"] == 3
    assert report["pending"][0]["assumption_ids"] == [
        "spatial-boundary-D1-profile",
        "spatial-boundary-D2-profile",
        "spatial-boundary-Dhalf-profile",
    ]


def test_one_assumption_id_asking_two_questions_stays_two_items() -> None:
    """The converse, and it is live: ``dose-salt-form`` on two certificates, different doses.

    Merging those would publish one item stating a conversion the other certificate did not make.
    """
    a = _cert(_assumption(id="dose-salt-form", chosen="779.9 mg"), title="one")
    b = _cert(_assumption(id="dose-salt-form", chosen="292.45 mg"), title="two")
    report = queue_report(_pairs(a, b))
    assert report["pending_count"] == 2


def test_an_id_the_certificate_names_is_honored_and_flagged_as_such() -> None:
    named = _cert(_assumption(verification_item="verify:by-hand"))
    derived = _cert(_assumption(description="unnamed"), title="other")
    report = queue_report(_pairs(named, derived))
    by_id = {item["id"]: item for item in report["pending"]}
    assert by_id["verify:by-hand"]["linked"] is True
    other = next(i for i in report["pending"] if i["id"] != "verify:by-hand")
    # A derived id appears in no certificate, so it is not what a reader greps for — and the
    # report says so rather than printing the two kinds of id alike.
    assert other["linked"] is False
    assert other["id"].startswith("verify:")


def test_one_named_id_carrying_two_different_questions_is_refused() -> None:
    a = _cert(_assumption(verification_item="verify:x", chosen="1.2"), title="one")
    b = _cert(_assumption(verification_item="verify:x", chosen="9.9"), title="two")
    with pytest.raises(ValueError, match="two different questions"):
        queue_from_certificates(_pairs(a, b))


# --- what it must not change --------------------------------------------------------------


def test_escalation_changes_no_verdict() -> None:
    """A load-bearing assumption already withholds a clean pass, so opening its item moves nothing.

    That is the property that makes escalating everything safe: an escalation that could downgrade
    a verdict would be a reason to escalate less.
    """
    cert = _cert(_assumption())
    before = cert.overall
    queue_report(_pairs(cert))
    assert cert.overall is before is OverallVerdict.PARTIALLY_REPRODUCED


def test_the_report_is_deterministic() -> None:
    certs = [_cert(_assumption(id=f"a{n}", description=f"d{n}"), title=f"p{n}") for n in range(4)]
    pairs = _pairs(*certs)
    assert queue_report(pairs) == queue_report(list(reversed(pairs)))


# --- what it is for -----------------------------------------------------------------------


def test_depends_on_names_digests_the_ledger_can_re_issue() -> None:
    """``reverify_dependents`` looks its dependents up in the ledger by digest, so these must be
    the digests the ledger keys on and not some other identifier."""
    from reprolith import CertificateLedger

    cert = _cert(_assumption())
    ledger = CertificateLedger()
    digest = ledger.issue(cert)
    queue, _, _ = queue_from_certificates([(digest, cert)])
    (item,) = queue.pending()
    assert item.depends_on == (digest,)
    assert ledger.get(item.depends_on[0]) is cert


def test_a_superseded_certificate_is_not_a_live_dependency() -> None:
    """A retracted result does not rank a question; the query surface filters before deriving."""
    from reprolith import CertificateLedger

    first = _cert(_assumption())
    ledger = CertificateLedger()
    ledger.issue(first)
    replacement = build_certificate(
        paper=PaperIdentity(title="t"),
        engine_pin=PIN,
        assessments=[
            ClaimAssessment(claim_id="c1", quantity="AUC", verdict=Verdict.REPRODUCED,
                            source_location="T1", assumption_qualified=True)
        ],
        assumptions=[_assumption()],
        supersedes=first,
    )
    ledger.issue(replacement)
    from reprolith.catalog import Catalog
    from reprolith.query import ReprolithQuery

    report = ReprolithQuery(Catalog(), ledger).verification_queue()
    assert report["standing_certificates"] == 1
    assert report["pending"][0]["depends_on"] == [certificate_digest(replacement)]


def test_the_committed_repository_has_a_queue_and_it_is_not_empty() -> None:
    query, _ = load_repository("datasets/milestone", aggregate=True)
    report = query.verification_queue()
    assert report["pending_count"] >= 1
    top = report["pending"][0]
    # Impact-ordered, and the metformin time unit is what four standing certificates rest on.
    assert top["id"] == "verify:time-unit-of-the-Zake2021-deposits"
    assert top["impact"] == 4
    assert all(
        report["pending"][i]["impact"] >= report["pending"][i + 1]["impact"]
        for i in range(len(report["pending"]) - 1)
    )
    # No number is invented for a field nothing measured.
    assert all(item["margin"] is None for item in report["pending"])


# --- the published page -------------------------------------------------------------------


def test_the_registry_page_states_what_the_whole_set_rests_on() -> None:
    """Each card names its own certificate's assumptions; the page named none of them together.

    A reader wanting to know what this registry rests on had to open every card and merge the
    answers by eye, and would still not learn that one question carries four of the certificates.
    """
    from reprolith import render_registry

    page = render_registry([("ode-pkpd", _cert(_assumption(id="k", description="the time unit")))])
    assert "Awaiting expert review" in page
    assert "the time unit" in page


def test_the_committed_registry_page_carries_the_queue() -> None:
    page = (Path(__file__).parent.parent / "datasets" / "registry.html").read_text(encoding="utf-8")
    query, _ = load_repository("datasets/milestone", aggregate=True)
    report = query.verification_queue()
    assert "Awaiting expert review" in page
    # The page and the two queried surfaces answer from one derivation, so a regenerated registry
    # that disagreed with `reprolith verification-queue` about the count fails here.
    assert f"{report['pending_count']} load-bearing values" in page
    assert f"{report['standing_certificates']} standing certificates" in page
    assert f"{report['engine_limits_count']} more load-bearing values" in page


def test_a_page_with_nothing_load_bearing_shows_no_banner() -> None:
    """An empty section reading "awaiting expert review" over nothing is worse than no section."""
    from reprolith import render_registry

    page = render_registry([("ode-pkpd", _cert())])
    assert "Awaiting expert review" not in page


# --- who can actually answer it -----------------------------------------------------------


def test_an_engine_limit_is_not_listed_as_awaiting_expert_review() -> None:
    """Six of this repository's eight load-bearing assumptions are Reprolith's own limits.

    The spatial solver implements one boundary condition; the stochastic class judges an ensemble
    it drew itself. No expert confirming anything closes either, and the first version of this
    report ranked them beside the two questions an expert *can* settle — so five of seven items
    read as waiting on a person.
    """
    expert = _cert(_assumption(id="dose", description="which salt"), title="one")
    ours = _cert(
        _assumption(id="boundary", description="this solver has one boundary", author_can_close=False),
        title="two",
    )
    report = queue_report(_pairs(expert, ours))
    assert [i["assumption_ids"] for i in report["pending"]] == [["dose"]]
    assert [i["assumption_ids"] for i in report["engine_limits"]] == [["boundary"]]


def test_one_closable_dependent_makes_the_whole_question_answerable() -> None:
    """Merged items can mix, and a question one author could close is a live question."""
    a = _cert(_assumption(author_can_close=False), title="one")
    b = _cert(_assumption(author_can_close=True), title="two")
    report = queue_report(_pairs(a, b))
    assert report["pending_count"] == 1
    assert report["engine_limits_count"] == 0
    assert report["pending"][0]["impact"] == 2


def test_the_committed_repository_splits_the_way_its_certificates_say() -> None:
    query, _ = load_repository("datasets/milestone", aggregate=True)
    report = query.verification_queue()
    # Counted off the certificates rather than written here, so a new class whose assumption is an
    # engine limit lands on the right side of the split without this number being edited.
    limits = {
        assumption.id
        for _, cert in query.ledger.items()
        for assumption in cert.assumptions
        if assumption.load_bearing and not assumption.author_can_close
    }
    listed = {aid for item in report["engine_limits"] for aid in item["assumption_ids"]}
    assert listed == limits
    assert report["pending_count"] >= 1  # and the expert-answerable half is not empty


# --- the gap report and the queue must not disagree ----------------------------------------


def test_the_gap_report_says_awaiting_review_for_every_answerable_assumption() -> None:
    """It used to depend on whether somebody had written an id into the file.

    Four metformin certificates name `verify:time-unit-of-the-Zake2021-deposits`, and the
    salt-form assumption beside them — equally queued, equally answerable — said nothing. Two
    published surfaces disagreeing about whether the same kind of value is under review.
    """
    from reprolith.render import gap_items

    named = _cert(_assumption(id="a", verification_item="verify:by-hand"))
    plain = _cert(_assumption(id="b", description="unnamed"), title="two")
    limit = _cert(_assumption(id="c", description="ours", author_can_close=False), title="three")
    def needs(cert):
        return " ".join(i["needs"] for i in gap_items(cert) if i["claim_id"] is None)

    assert "awaiting expert confirmation (verify:by-hand)" in needs(named)
    assert "awaiting expert confirmation" in needs(plain)
    # And an engine limit is not awaiting anyone, so it does not say it is.
    assert "awaiting expert confirmation" not in needs(limit)
