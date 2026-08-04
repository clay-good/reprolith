"""The inline FBA linter check: `lint_objective` (spec: mcp-server — "Deterministic linter mode").

The constraint-based counterpart of `lint_curve`. It needs the ``engine`` extra (python-libsbml
for fbc ingest) and the ``fba`` extra (scipy's LP solver) — *not* COPASI — so it is tested apart
from the simulate-based linter, on the real E. coli core model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the 'fba' extra (scipy) is not installed")

from reprolith import Verdict, lint_objective  # noqa: E402

_SBML = (Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml").read_text(
    encoding="utf-8"
)
_KNOWN_GROWTH_RATE = 0.873922


def test_reproduces_the_known_optimum_with_the_scope_flag() -> None:
    result = lint_objective(_SBML, reported=_KNOWN_GROWTH_RATE)
    assert result.verdict is Verdict.REPRODUCED
    assert result.method == "scalar-relative-error"
    # The verdict never travels as a bare boolean — the inescapable scope flag rides with it.
    assert result.scope.to_dict()["human"]


def test_a_wrong_reported_optimum_fails() -> None:
    assert lint_objective(_SBML, reported=1.5).verdict is Verdict.FAILED


def test_is_deterministic() -> None:
    assert lint_objective(_SBML, reported=_KNOWN_GROWTH_RATE).to_dict() == lint_objective(
        _SBML, reported=_KNOWN_GROWTH_RATE
    ).to_dict()


def test_the_medium_argument_changes_the_check() -> None:
    # Shutting oxygen off (anaerobic) drops the optimum; the reported anaerobic value reproduces
    # only when the linter is told the medium, so `medium` genuinely drives the verdict.
    anaerobic = lint_objective(_SBML, reported=0.211663, medium={"R_EX_o2_e": 0.0})
    assert anaerobic.verdict is Verdict.REPRODUCED
    # The same reported value against the default aerobic medium is nowhere close.
    assert lint_objective(_SBML, reported=0.211663).verdict is Verdict.FAILED


def test_a_medium_naming_an_unknown_reaction_is_surfaced() -> None:
    with pytest.raises(ValueError, match="does not contain"):
        lint_objective(_SBML, reported=_KNOWN_GROWTH_RATE, medium={"R_EX_not_a_reaction_e": 5.0})
