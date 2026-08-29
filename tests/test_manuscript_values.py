"""The check that would have caught the corpus's one wrong reference value.

Metformin's 500 mg plasma Cmax was recorded as 6.2 nmol/mL and cited to a table that prints 6.1 —
and it passed, because both are inside a 5% tolerance on the same simulated peak. From inside the
pipeline a wrong reference that still passes is invisible. This asks the one question that is not
inside the pipeline: is the number you state printed in the table you cite?

Pure standard library, so it runs in the dependency-free core gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import check_claim_values, unsupported_claims

_ROOT = Path(__file__).parent.parent
_TABLES = json.loads(
    (_ROOT / "datasets" / "manuscripts" / "BIOMD0000001028_tables.json").read_text(encoding="utf-8")
)["tables"]


def _claim(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "claim_id": "Cmax-500mg",
        "reported": 6.1,
        "source_location": "Table 6, plasma row, 500 mg single PO dose",
    }
    record.update(overrides)
    return record


def test_the_historical_defect_is_reported() -> None:
    """6.2 against Table 6, and against the Table 4 the claim used to cite: neither prints it."""
    for cited in ("Table 6, plasma row", "Table 4, Zaharenko dataset"):
        (check,) = check_claim_values([_claim(reported=6.2, source_location=cited)], _TABLES)
        assert check.found is False, cited
        assert "is not printed" in check.detail


def test_the_corrected_value_is_accepted() -> None:
    (check,) = check_claim_values([_claim()], _TABLES)
    assert check.found is True and "6.1 is printed in Table 6" in check.detail


def test_the_committed_claims_all_check_out() -> None:
    """The corpus itself, through the capability rather than through a bespoke test."""
    claims = json.loads((_ROOT / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8"))
    records = claims["entries"]["BIOMD0000001028"]["claims"]
    checks = check_claim_values(records, _TABLES)
    assert unsupported_claims(checks) == ()
    assert all(check.found is True for check in checks), [c.detail for c in checks]


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("Figure 3B", "cites no table"),
        ("Table S2 of the supplement", "was not supplied"),
        ("", "cites no table"),
    ],
)
def test_a_claim_this_cannot_check_is_unchecked_not_wrong(source: str, reason: str) -> None:
    """An absence of evidence is not evidence of absence, and the two must not share a list."""
    (check,) = check_claim_values([_claim(source_location=source)], _TABLES)
    assert check.found is None
    assert reason in check.detail
    assert unsupported_claims([check]) == ()


def test_a_value_is_matched_as_the_paper_prints_it_not_by_rounding() -> None:
    """Rounding would accept the number the paper *would have* printed, not the one it did."""
    (near,) = check_claim_values([_claim(reported=6.13)], _TABLES)
    assert near.found is False
    # A different spelling of the same number is the same number, though.
    (same,) = check_claim_values([_claim(reported=6.10)], _TABLES)
    assert same.found is True


def test_a_thousands_separator_in_the_paper_still_matches() -> None:
    """Table 6 prints '7 235.1' and '1 268.9'; a claim states 7235.1."""
    tables = {"Table 6": {"rows": [["Kidney", "500", "7 235.1", "840.0"]]}}
    (check,) = check_claim_values(
        [_claim(reported=7235.1, source_location="Table 6")], tables
    )
    assert check.found is True


def test_an_unfilled_template_is_unchecked_rather_than_a_failure() -> None:
    """`reported` is null until the author writes it; that is not a wrong value."""
    (check,) = check_claim_values([_claim(reported=None)], _TABLES)
    assert check.found is None and "unfilled" in check.detail
    assert unsupported_claims([check]) == ()
