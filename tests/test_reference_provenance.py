"""What every published certificate is checked *against*, counted rather than described.

The front page divides this repository's certificates in two: the ones whose reference is a number
a publication printed, and the ones whose reference is an independent tool or closed-form
mathematics re-running the same model file. That division is the single most important thing a
reader needs, because only the first kind says anything about a *paper*.

It was prose. Counting it found the sentence off by one: the E. coli core certificate is checked
against the maximal growth rate its own distributing publication reports — 0.873922 from Orth,
Fleming & Palsson (2010) — which is a published number, not a tool's answer, and it was inside the
"checked against an independent tool" count.

Every claim in every committed certificate is classified here from its own cited source, so the
next certificate added lands in one of the buckets and the sentence it changes fails.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")

#: The tools this repository re-runs a model under. Each names itself in the source it cites.
_TOOLS = ("COBRApy", "libRoadRunner", "CANA")


def _certificates() -> list[tuple[str, dict]]:
    found = [
        (path.relative_to(REPO / "datasets").as_posix(),
         json.loads(path.read_text(encoding="utf-8")))
        for path in sorted((REPO / "datasets").rglob("certificates/*.json"))
    ]
    assert found, "no committed certificates found; this check would pass vacuously"
    return found


def _kind(source: str) -> str:
    if any(tool in source for tool in _TOOLS):
        return "tool"
    if "closed-form" in source:
        return "mathematics"
    return "publication"


def test_every_certificate_is_checked_against_a_tool_mathematics_or_a_publication() -> None:
    """Three buckets, no fourth, and each certificate lands in exactly one of them."""
    by_kind: dict[str, list[str]] = {"tool": [], "mathematics": [], "publication": []}
    for name, content in _certificates():
        kinds = {_kind(a["source_location"]) for a in content["assessments"]}
        assert len(kinds) == 1, f"{name} mixes reference kinds: {sorted(kinds)}"
        by_kind[kinds.pop()].append(name)

    assert len(sum(by_kind.values(), [])) == 33
    assert len(by_kind["tool"]) == 22       # COBRApy 7, libRoadRunner 6, CANA 9
    assert len(by_kind["mathematics"]) == 6  # three stochastic, three spatial
    # Five against a published number: the four models the metformin paper deposited, and the
    # E. coli core growth rate its own distributing publication reports.
    assert len(by_kind["publication"]) == 5, sorted(by_kind["publication"])
    assert sorted(Path(name).stem for name in by_kind["publication"]) == [
        "BIOMD0000001027", "BIOMD0000001028", "BIOMD0000001029", "BIOMD0000001039",
        "e_coli_core",
    ]


def test_the_front_page_states_that_division_in_the_numbers_it_is() -> None:
    """The sentence a reader takes the corpus's reach from, held to the corpus."""
    assert "twenty-eight" in README, (
        "the README no longer says how many certificates are checked against a tool or against "
        "mathematics; that count is the reader's whole guide to what this corpus reaches"
    )
    # And the E. coli core exception is named rather than folded into either side silently.
    assert "0.873922" in README or "E. coli core" in README
