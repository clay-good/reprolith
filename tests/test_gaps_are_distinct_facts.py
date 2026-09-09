"""The "what was missing" report, read as the page and the page's reader rather than as a list.

`gap_items` is one item per claim, which is the right *data*: a machine consumer joins a shortfall
to the claim it blocks. Both renderings printed it straight, and on the twice-daily metformin entry
that is fifty-five bullets carrying thirteen distinct facts. Forty-three of them say the identical
sentence about one assumption; the three findings that differ — a protocol the artifact runs less of
than the paper states, a table this engine believes is wrong, a set of units nothing declares — sat
underneath them, at the bottom of a fifty-seven-line page.

That is the rule the neighbouring pre-submission fix list already follows, in the spec's own words:
one fix that blocks many claims is one item naming all of them, since repeating it per claim buries
the fixes that differ among the rows that do not. The gap report is where that rule was written down
and not applied.

Only *identical* text collapses. Two claims that missed by different amounts are two facts.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith.cli import run
from reprolith.mcp_server import default_data_dir, load_repository

_ROOT = Path(__file__).parent.parent
_TWICE_DAILY = "BIOMD0000001029"


def _digest() -> str:
    query, _catalog = load_repository(default_data_dir(), aggregate=True)
    (digest,) = query.certificates_for(accession=_TWICE_DAILY)
    return digest


def test_the_terminal_report_says_a_repeated_sentence_once(capsys) -> None:
    assert run(["gaps", _digest()]) == 0
    out = capsys.readouterr().out
    assert out.count("reproduced only under an assumption Reprolith supplied") == 1
    assert "43 claim(s): reproduced only under an assumption" in out
    # Nothing is dropped: every claim that said it is named on the line under it.
    assert "claims: Cmax-1000mg-twice-daily, " in out


def test_the_three_findings_that_differ_are_no_longer_buried(capsys) -> None:
    """What the collapse is for. Each of these is a separate statement about a separate cause."""
    assert run(["gaps", _digest()]) == 0
    out = capsys.readouterr().out
    assert out.count("apparent-manuscript-error") == 3
    assert out.count("artifact-runs-less-of-the-protocol-than-the-paper-states") == 6
    # The whole report now fits on a screen, which is the difference between a reader seeing the
    # three findings and scrolling past them.
    assert len(out.splitlines()) < 20, out


def test_two_claims_that_missed_by_different_amounts_stay_two_lines(capsys) -> None:
    assert run(["gaps", _digest()]) == 0
    out = capsys.readouterr().out
    assert "relative error 0.2012" in out and "relative error 0.2008" in out


def test_the_header_counts_both_populations(capsys) -> None:
    """A collapsed list must not read as a shorter certificate: items and distinct facts differ."""
    assert run(["gaps", _digest()]) == 0
    assert "55 item(s), 13 distinct" in capsys.readouterr().out


def test_the_json_still_carries_one_item_per_claim(capsys) -> None:
    """The collapse is a rendering. An agent joining a shortfall to the claim it blocks needs the
    per-claim items, and this surface promises the terminal and the agent read one computation."""
    assert run(["gaps", _digest(), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["gaps"]) == 55
    assert sum(
        1 for g in payload["gaps"]
        if g["needs"].startswith("reproduced only under an assumption")
    ) == 43


def test_the_public_page_does_not_print_one_sentence_forty_three_times() -> None:
    """And it never carried a claim id, so those bullets could not even be told apart."""
    page = (_ROOT / "datasets" / "registry.html").read_text(encoding="utf-8")
    assert "<li>43 claims: reproduced only under an assumption" in page
    # Nine cards carry the sentence, one bullet each. This entry alone used to print it
    # forty-three times, so the whole page now says it fewer times than one card once did.
    assert page.count("reproduced only under an assumption Reprolith supplied") == 9
    # The summary still counts what the certificate holds, not what the list shows.
    assert "what was missing (55)" in page
