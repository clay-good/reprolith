"""A second engine for the constraint-based class: Reprolith's LP against COBRApy's.

This class had no second registered engine, so every corroboration surface reported it as
*unchecked* — an absence rather than a pass, correctly, and one that did not have to stay. COBRApy
is a different SBML reader in front of a different LP backend, so agreement between the two is
corroboration of the same kind the ODE classes already publish (roadmap #5).

What is compared is the **objective value**, and that is the substance of the design rather than a
convenience: a linear program's optimum is unique, the flux vector attaining it usually is not, so
comparing flux distributions would call two correct solvers engine-sensitive on any model with
alternate optima — which is most of them.

Needs the ``engine`` (libSBML), ``fba`` (scipy) and ``corroborate`` (COBRApy) extras; skips
without any of them.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")
pytest.importorskip("cobra", reason="the optional 'corroborate' extra (COBRApy) is not installed")

from reprolith.corroboration import corroborate_objective  # noqa: E402

_CB = Path(__file__).parent.parent / "datasets" / "constraint_based"
_CROSS = _CB / "cross_validation"
_MILESTONE = _CB / "milestone"


def _model(accession: str) -> str:
    if accession == "e_coli_core":
        return (_CB / "e_coli_core.xml").read_text(encoding="utf-8")
    return gzip.decompress((_CROSS / f"{accession}.xml.gz").read_bytes()).decode("utf-8")


def _committed() -> dict:
    return json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))


def test_every_certified_model_is_covered_by_the_committed_record() -> None:
    """The population is the certificates, not whatever the record happens to hold.

    A record built from a list that drifts from the certificate directory publishes "all
    engine-independent" over a class in which some models were never re-run.
    """
    certified = {p.stem for p in (_MILESTONE / "certificates").glob("*.json")}
    assert certified, "expected committed constraint-based certificates"
    assert set(_committed()) == certified


@pytest.mark.parametrize("accession", sorted(_committed()))
def test_the_committed_bound_is_reproducible_and_never_better_than_measured(accession: str) -> None:
    stored = _committed()[accession]
    result = corroborate_objective(_model(accession))

    assert result.engines == ("scipy-linprog", "cobrapy")
    assert result.stable and stored["engine_independent"]
    # The published number is a bound, so re-measuring may land under it and must never land over
    # it: that is the one direction in which the committed artifact would be false.
    assert result.distance <= stored["distance_at_most"]
    assert result.distance_bound() <= stored["distance_at_most"]


def test_the_record_names_the_builds_it_was_measured_on() -> None:
    for accession, row in _committed().items():
        assert row["engines"] == ["scipy-linprog", "cobrapy"], accession
        assert all(version for version in row["engine_versions"]), accession


def test_an_impossibly_tight_criterion_reports_engine_sensitive() -> None:
    # The stable/sensitive decision answers to the declared criterion rather than to a hope: at
    # zero tolerance even a 1e-15 difference between two LP backends is flagged, which is the
    # branch that has to work for the reported verdict to mean anything.
    result = corroborate_objective(_model("e_coli_core"), rel_tol=0.0)
    assert not result.stable
    assert "engine-sensitive" in result.summary()


def test_a_model_neither_solver_can_optimize_is_not_reported_as_a_distance() -> None:
    """Infeasible on one side is a disagreement about whether there is a number at all.

    Published as a distance it would read as two solvers differing about a value; the two are not
    the same finding, and only one of them is about the model's behaviour.
    """
    from reprolith.fba import InfeasibleFba

    # The maintenance reaction's floor raised past anything the distributed medium can supply.
    # It stays a valid SBML document — the bound is a parameter, and only its value changes — so
    # both implementations read the same model and neither can solve it.
    original = _model("e_coli_core")
    sbml = original.replace(
        '<parameter id="R_ATPM_lower_bound" value="8.39"',
        '<parameter id="R_ATPM_lower_bound" value="1000"',
    )
    assert sbml != original, "the model no longer states its ATPM floor as a named parameter"
    with pytest.raises((InfeasibleFba, ValueError)):
        corroborate_objective(sbml)
