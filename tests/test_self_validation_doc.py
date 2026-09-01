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


def test_every_class_row_names_a_milestone_directory_that_exists() -> None:
    """A row pointing at a directory nobody generated is a track record with no evidence under it."""
    import re

    linked = set(re.findall(r"\]\(\.\./(datasets/[a-z_/]*milestone)/\)", _PAGE))
    assert linked, "the page links no milestone directories; this check would pass vacuously"
    for relative in sorted(linked):
        assert (_ROOT / relative).is_dir(), relative
