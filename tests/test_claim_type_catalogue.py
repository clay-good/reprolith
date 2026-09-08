"""The page listing what can be certified is the page the code says it is.

`docs/claim-types.md` answers a modeller's first question — "can it check the thing my paper
reports?" — and a document like that rots in one direction: a claim type is added and nobody
remembers the page. Then the capability exists and no reader can find it, which this repository has
shipped before (the FROG fingerprint, the basin of attraction, the noise statistics were all
computed long before anything could certify them, and nothing said so).

So the page is held to the exports, in both directions: a claim type missing from it fails, and a
row naming a type that does not exist fails too.
"""

from __future__ import annotations

import re
from pathlib import Path

import reprolith
from reprolith import constraint_based

_PAGE = (Path(__file__).parent.parent / "docs" / "claim-types.md").read_text(encoding="utf-8")

#: Claim types that are not *reproduction targets*: a dossier's record of a claim, and the record of
#: one a budget left unattempted. Neither is a thing a front end judges.
_NOT_TARGETS = {"DossierClaim", "UnattemptedClaim"}


def _exported() -> set[str]:
    package = {name for name in reprolith.__all__ if name.endswith("Claim")}
    # The constraint-based ones live in their own module rather than the package root.
    module = {name for name in dir(constraint_based) if name.endswith("Claim")}
    return (package | module) - _NOT_TARGETS


def test_every_claim_type_has_a_row() -> None:
    missing = sorted(name for name in _exported() if f"`{name}`" not in _PAGE)
    assert not missing, (
        "docs/claim-types.md does not list: " + ", ".join(missing) +
        " — a capability a reader cannot find is one this repository has shipped before"
    )


def test_every_row_names_a_claim_type_that_exists() -> None:
    listed = set(re.findall(r"^\| `(\w+Claim)`", _PAGE, re.MULTILINE))
    unknown = sorted(listed - _exported())
    assert not unknown, f"docs/claim-types.md lists claim types that do not exist: {unknown}"


def test_the_page_says_how_each_one_abstains() -> None:
    """The column that makes it a description of behaviour rather than a feature list."""
    rows = [line for line in _PAGE.splitlines() if line.startswith("| `") and line.count("|") >= 5]
    assert len(rows) >= len(_exported())
    for row in rows:
        cells = [cell.strip() for cell in row.split("|")[1:-1]]
        assert all(cells), f"an empty cell in: {row}"


def test_the_boundary_is_stated_rather_than_left_to_be_noticed() -> None:
    """Several quantities this engine computes carry no claim type, on purpose. A page listing only
    what exists reads as a complete account of what the engine can do."""
    for quantity in ("synthetic lethal", "production envelope", "shadow price", "parsimonious"):
        assert quantity in _PAGE


def test_the_front_page_states_the_number_this_page_lists() -> None:
    """The README tells a reader how many kinds of result can be certified, and that is a count.

    Every other count on that page is held to the repository — the certificates, the split between
    a publication's numbers and a tool's — and this one is the newest.
    """
    import re

    # Data rows: a claim type in backticks, or the one row for a claim a *dossier* states rather
    # than a class front end (an objective value), which has no type of its own.
    rows = len(re.findall(r"^\| (?:`\w*Claim`|an )", _PAGE, re.MULTILINE))
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    words = {15: "Fifteen", 16: "Sixteen", 17: "Seventeen", 18: "Eighteen", 19: "Nineteen"}
    assert f"{words[rows]} kinds of result" in readme, (
        f"docs/claim-types.md lists {rows} kinds and the README says otherwise"
    )
