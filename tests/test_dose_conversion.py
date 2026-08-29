"""Every dose Reprolith derives, checked against the conversion it says it used.

The metformin claims run at a free-base dose Reprolith computes from the paper's stated
hydrochloride dose — the assumption block gives the factor, 129.16/165.62. Nothing checked the
arithmetic, and the corpus ended up spelling the 1500 mg arm as **1169.85** where that conversion
gives 1169.79. It reproduced: 18.5611 against the paper's 18.5, a 0.33% error inside a 5%
tolerance, so no verdict and no gate could see it. A wrong number that still passes is invisible
from inside the pipeline — the same shape as the reference value that was not in the paper.

Checked as an exact rounding rather than within a tolerance, because a relative bound cannot tell
a legitimate one-decimal rounding from that typo: both are 5.5e-5 away from the true value.

Pure standard library, so this runs in the dependency-free core gate.
"""

from __future__ import annotations

import json
from pathlib import Path

_CLAIMS = json.loads(
    (Path(__file__).parent.parent / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8")
)

#: The factor the assumption block states: metformin free base over metformin hydrochloride.
_FREE_BASE_OVER_HCL = 129.16 / 165.62

#: The hydrochloride doses this paper reports, in mg.
_STATED = (250, 375, 500, 750, 1000, 1500)


def _overrides() -> list[tuple[str, str, float]]:
    """Every parameter value any committed claim sets, as (accession, claim, value)."""
    found: list[tuple[str, str, float]] = []
    for accession, entry in _CLAIMS["entries"].items():
        for claim in entry["claims"]:
            sources = [claim.get("parameter_overrides") or {}]
            sources += [s.get("parameter_overrides") or {} for s in claim.get("schedule", [])]
            for source in sources:
                for value in source.values():
                    found.append((accession, claim["claim_id"], float(value)))
    return found


def test_every_dose_is_a_rounding_of_the_conversion_the_certificate_states() -> None:
    allowed = {
        rounded
        for stated in _STATED
        for rounded in (
            round(stated * _FREE_BASE_OVER_HCL, 1), round(stated * _FREE_BASE_OVER_HCL, 2)
        )
    }
    overrides = _overrides()
    assert overrides, "no claim sets a dose; this check would pass vacuously"
    for accession, claim_id, value in overrides:
        assert value in allowed, (accession, claim_id, value, sorted(allowed))


def test_one_stated_dose_has_one_spelling() -> None:
    """Two roundings of one dose are two derived models in the exported archive, and two numbers
    a reader has to reconcile. 1000 mg was written 779.9 in one claim and 779.86 in another."""
    by_dose: dict[int, set[float]] = {}
    for _, _, value in _overrides():
        for stated in _STATED:
            exact = stated * _FREE_BASE_OVER_HCL
            if value in (round(exact, 1), round(exact, 2)):
                by_dose.setdefault(stated, set()).add(value)
    for stated, spellings in by_dose.items():
        assert len(spellings) == 1, (stated, sorted(spellings))


def test_the_assumption_states_the_values_the_claims_actually_run() -> None:
    """The block a reader checks the arithmetic against has to name the numbers that ran."""
    running = {value for _, _, value in _overrides()}
    for entry in _CLAIMS["entries"].values():
        for assumption in entry.get("assumptions", ()):
            quoted = {
                float(token)
                for token in assumption["chosen"].replace("(", " ").replace(")", " ").split()
                if token.replace(".", "", 1).isdigit() and "." in token
            }
            named = quoted & running
            assert named, (assumption["id"], sorted(quoted), sorted(running))
            # And nothing it names is a dose no claim runs at.
            stale = {v for v in quoted if 100.0 < v < 2000.0} - running
            assert not stale, ("the assumption names doses no claim runs at", sorted(stale))
