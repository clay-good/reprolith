"""The README's checkable claims, checked.

The README is the first thing anyone reads and the easiest thing to leave behind. Two of its
claims are mechanically verifiable against the repository, and both have a failure mode that is
invisible on inspection: a command that was renamed still reads fine in a code block, and a count
of published certificates stays plausible forever.

Pure stdlib, so this runs on the dependency-free core gate.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reprolith.cli import build_parser

_ROOT = Path(__file__).parent.parent
_README = (_ROOT / "README.md").read_text(encoding="utf-8")


def _subcommands() -> set[str]:
    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return set(action.choices)


def test_every_command_the_readme_shows_is_a_command() -> None:
    """A renamed command still reads perfectly in a code block. Someone copying the line finds out
    instead — which is the whole cost of a README nobody checks."""
    shown = {
        match.group(1)
        for match in re.finditer(r"^reprolith ([a-z][a-z-]*)", _README, re.MULTILINE)
    }
    assert shown, "the README shows no CLI commands; this check would pass vacuously"
    unknown = shown - _subcommands()
    assert not unknown, f"the README shows commands the CLI does not have: {sorted(unknown)}"


def test_the_readme_sends_a_reader_to_help_for_the_commands_it_omits() -> None:
    """It shows a useful subset on purpose, so the omission has to be signposted rather than read
    as the whole surface."""
    omitted = _subcommands() - {
        match.group(1)
        for match in re.finditer(r"^reprolith ([a-z][a-z-]*)", _README, re.MULTILINE)
    }
    assert omitted, "the README now shows every command; drop this check rather than weakening it"
    assert "reprolith --help" in _README


#: How the README words each certificate count it states. A count that changes makes the sentence
#: wrong in a way no reader can detect, so the number and the word are pinned together.
#: Longest first: "thirty" is a substring of "thirty-one", so a shorter spelling that happens to
#: be a prefix would match the longer sentence and check the wrong number.
_WORDED_COUNTS = {"thirty-one": 31, "thirty-two": 32, "thirty-three": 33, "thirty": 30}


def test_the_published_certificate_count_the_readme_states_is_the_count() -> None:
    published = len(list(_ROOT.glob("datasets/**/milestone/certificates/*.json")))
    assert published > 0, "no published certificates found; this check would pass vacuously"
    for word, number in _WORDED_COUNTS.items():
        if word in _README:
            assert published == number, (
                f"the README says '{word}' published certificates and the repository has "
                f"{published}; update the sentence, or this file's _WORDED_COUNTS if the wording "
                "changed"
            )
            return
    raise AssertionError(
        "the README no longer states a certificate count in any wording this knows; add it to "
        "_WORDED_COUNTS so the claim stays checked"
    )


def test_the_front_pages_reproduction_split_is_the_certificates_split() -> None:
    """The strongest sentence on the page — "fifty-seven reproduce, six do not" — is checkable.

    It is also the one most likely to go stale: every claim added to the corpus moves it, and a
    front page that overstates how much reproduces is the single worst thing this repository could
    publish about itself.
    """
    import json

    reproduced = missed = 0
    for path in _ROOT.glob("datasets/milestone/certificates/*.json"):
        certificate = json.loads(path.read_text(encoding="utf-8"))
        for assessment in certificate["assessments"]:
            if assessment["verdict"] == "reproduced":
                reproduced += 1
            else:
                missed += 1
    assert (reproduced, missed) == (71, 6), (reproduced, missed)
    assert "Seventy-one reproduce. Six do not" in _README
    assert "**seventy-seven claims**" in _README and reproduced + missed == 77


def test_the_front_page_does_not_claim_the_extraction_it_has_not_built() -> None:
    """It reads a paper's tables and says so; it does not read prose and must keep saying so.

    The paragraph describing sixty-three claims read from a paper sits four lines above the one
    admitting extraction is unbuilt, and an edit to either can quietly turn that into a
    contradiction.
    """
    assert "Reading claims out of prose is not built at all." in _README
    assert "at scale* is the piece that is not built" in _README
