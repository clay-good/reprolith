"""The track-record page's headline, checked against the record it summarizes.

`docs/self-validation.md` is the credibility claim: it is where a reader goes to find out how often
Reprolith's blind verdicts matched independently-established ground truth. Every number on it is a
summary of `datasets/**/milestone/agreement_report.json`, and nothing checked that the summary is
still the record's.

It had drifted, in the direction that flatters. The PK/PD row said "1 partially-reproduced + 30
honest abstentions, **0 wrong verdicts**" while the committed report held one *reproduced* matching
its label, 27 abstentions, and three verdicts that differ from theirs. All three differ in the
stricter direction — a withheld pass, never a false one — which is worth saying and is not what
"zero wrong verdicts" says.

Pure stdlib, so it runs on the dependency-free core gate.
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_PAGE = (_ROOT / "docs" / "self-validation.md").read_text(encoding="utf-8")
#: The README repeats the same summary in one line, and repeated numbers drift apart. It is
#: checked against the same record here rather than in a second place with its own idea of it.
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
#: And the loop record's prose account of the same run, which drifted the same way and by the same
#: mechanism: a number written down once, beside data that kept moving.
_LOOP = (_ROOT / "docs" / "discipline-loop.md").read_text(encoding="utf-8")
#: And the walkable milestone's own README, which a stranger is invited to follow end to end. It
#: held the same run's numbers in a table, a headline, a section title and three sentences.
_MILESTONE = (_ROOT / "datasets" / "milestone" / "README.md").read_text(encoding="utf-8")
_REPORT = json.loads(
    (_ROOT / "datasets" / "milestone" / "agreement_report.json").read_text(encoding="utf-8")
)


def _split() -> tuple[int, int, int]:
    """Matched / abstained / confidently-different, the same split every read surface uses."""
    from reprolith.agreement import summarize_report

    counts = summarize_report(_REPORT)
    return counts["matched"], counts["abstained"], counts["other"]


def test_the_page_states_the_counts_the_committed_report_holds() -> None:
    matched, abstained, other = _split()
    assert (matched, abstained, other) == (1, 27, 3), "regenerate the milestone, then this page"
    assert f"{abstained} honest abstentions" in _PAGE
    assert f"{other} verdicts stricter than the label" in _PAGE
    assert f"abstained on {abstained} of {matched + abstained + other} entries" in _PAGE


def test_the_page_does_not_claim_a_clean_sheet_it_no_longer_has() -> None:
    """The specific sentence that drifted, refused by name.

    "Zero wrong verdicts" collapses two different facts — no false pass, and no disagreement at all
    — and the second stopped being true. The first is the one that matters and the page now says
    exactly it.
    """
    matched, abstained, other = _split()
    for page in (_PAGE, _README):
        if other:
            assert "0 wrong verdicts" not in page
            assert "zero verdicts wrong" not in page
            assert "zero wrong verdicts" not in page
    assert "no false pass" in _PAGE
    # The README states the same split in one line, and two places holding one number is how this
    # drifted in the first place.
    assert f"({abstained} abstentions" in _README
    assert "three verdicts stricter than their label" in _README and other == 3


def test_the_loop_record_states_the_same_split_as_the_report() -> None:
    """A third page summarizing one run in prose, drifted the same way and for the same reason.

    It said "What the 31 disagreements say", "30 abstentions", and "1 more-careful verdict". There
    are thirty disagreements, twenty-seven abstentions, and three careful verdicts — the three
    human-dosed metformin models, each qualified by the same salt-form assumption. The fourth,
    the mouse model, needed no conversion and is the one entry that matches its label.
    """
    matched, abstained, other = _split()
    assert f"## What the {abstained + other} disagreements say" in _LOOP
    assert f"**{abstained} abstentions**" in _LOOP
    assert f"**{other} more-careful verdicts**" in _LOOP
    assert matched == 1


def test_the_milestone_readme_states_the_same_split_as_the_report_beside_it() -> None:
    """The fourth page summarizing one run, and the one that sits in the directory it describes.

    It said one certified reproduction and thirty abstentions, headlined "Why 0/31 is the honest
    result", and named a single more-careful verdict. There are four certificates — one clean
    `reproduced` and three `partially-reproduced` — twenty-seven abstentions, and raw agreement of
    1/31. Its own `agreement_report.json` is in the same directory.
    """
    matched, abstained, other = _split()
    total = matched + abstained + other
    assert f"Why {matched}/{total} is the honest result" in _MILESTONE
    assert f"**{abstained} abstentions.**" in _MILESTONE
    assert f"| `blocked` | {abstained} |" in _MILESTONE
    assert f"| `partially-reproduced` | {other} |" in _MILESTONE
    assert f"| `reproduced` | {matched} |" in _MILESTONE
    # And the count of published certificates the page promises a reader they will find.
    certificates = list((_ROOT / "datasets" / "milestone" / "certificates").glob("*.json"))
    assert len(certificates) == matched + other == 4


def test_the_committed_data_states_the_split_its_own_report_holds() -> None:
    """Two data files carry the same summary in prose, and prose in a JSON file drifts like any.

    The labelled set's own `caveat` is what every page cites as authoritative about how to read
    these numbers, and it said "30 of 31 entries are blocked, with zero wrong verdicts". The loop
    record's abstention note had the count corrected and left "raw agreement 0/31" behind it. Both
    are read by tests for their schema and by nothing for their arithmetic.
    """
    matched, abstained, other = _split()
    total = matched + abstained + other

    caveat = json.loads(
        (_ROOT / "datasets" / "pkpd_test_set.json").read_text(encoding="utf-8")
    )["caveat"]
    assert f"{abstained} of {total} entries are blocked" in caveat
    assert "zero wrong verdicts" not in caveat

    notes = json.loads(
        (_ROOT / "datasets" / "loop_notes.json").read_text(encoding="utf-8")
    )["notes"]
    abstention = next(n for n in notes if n["id"] == "pkpd-abstained-no-extracted-claims")
    assert f"{abstained} of the thirty-one" in abstention["note"]
    assert f"raw agreement to {matched} of {total}" in abstention["note"]
    assert "0/31" not in abstention["note"]


def test_every_class_readme_states_its_own_report_s_agreement() -> None:
    """The generalization of everything above, so the next class to move is caught by the first.

    Only PK/PD drifted, because it is the only class whose numbers have moved: the other five each
    say `8/8`, `6/6`, `9/9`, `3/3`, `3/3`, and each matches its own report exactly. That is luck
    rather than a check — a class gaining an entry, or losing agreement on one, would leave its
    README saying the old ratio with nothing to notice, which is precisely how PK/PD's four pages
    got where they were.

    A README carrying no `matched/total` ratio is skipped rather than failed: the PK/PD one states
    its split in a table instead, and the tests above hold it to that.
    """
    import re

    from reprolith.agreement import summarize_report
    from reprolith.mcp_server import milestone_certificate_dirs

    checked = 0
    for model_class, directory in sorted(milestone_certificate_dirs().items()):
        report = directory.parent / "agreement_report.json"
        readme = directory.parent / "README.md"
        if not report.is_file() or not readme.is_file():
            continue
        counts = summarize_report(json.loads(report.read_text(encoding="utf-8")))
        ratios = set(re.findall(r"\b(\d+)/(\d+)\b", readme.read_text(encoding="utf-8")))
        stated = {(int(a), int(b)) for a, b in ratios if int(b) == counts["total"]}
        if not stated:
            continue
        assert stated == {(counts["matched"], counts["total"])}, (model_class, stated, counts)
        checked += 1
    assert checked >= 5, f"only {checked} class READMEs state a ratio; this check is going quiet"


def test_every_class_row_names_a_milestone_directory_that_exists() -> None:
    """A row pointing at a directory nobody generated is a track record with no evidence under it."""
    import re

    linked = set(re.findall(r"\]\(\.\./(datasets/[a-z_/]*milestone)/\)", _PAGE))
    assert linked, "the page links no milestone directories; this check would pass vacuously"
    for relative in sorted(linked):
        assert (_ROOT / relative).is_dir(), relative
