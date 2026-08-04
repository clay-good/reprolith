"""Generic-kinetic class: the curve oracle carries a systems-biology model (spec: ode-pkpd reuse).

Reprolith's second ODE class is generic systems-biology (kinetic) models — the same time-course
reproduction as PK/PD, on biochemical reaction networks rather than compartmental drug models. This
checks that the shared simulate + curve oracle reproduce a curated, non-PK/PD kinetic model: the
Kholodenko2000 MAPK cascade (BioModels BIOMD0000000010), an oscillating signaling network.

Ground truth is an independent simulator: the reference MAPK_PP time-course in
``datasets/kinetic/mapk_reference_curve.json`` was computed by libRoadRunner (CVODE), which shares
no code with the COPASI engine Reprolith runs, so reproducing it is a genuine non-circular
cross-tool check — not COPASI agreeing with itself.

Needs the ``engine`` extra (python-copasi) to run the simulation; skips without it. libRoadRunner is
not needed here — it only generated the committed reference.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import Verdict, judge_curve, simulate  # noqa: E402

_DIR = Path(__file__).parent.parent / "datasets" / "kinetic"
_REFERENCE = json.loads((_DIR / "mapk_reference_curve.json").read_text(encoding="utf-8"))
_SBML = (_DIR / "BIOMD0000000010.xml").read_text(encoding="utf-8")


def _reprolith_curve() -> list[float]:
    _, values = simulate(
        _SBML, _REFERENCE["species"],
        duration=_REFERENCE["duration"], steps=_REFERENCE["steps"],
    )
    return list(values)


def test_reproduces_the_independent_simulators_trajectory() -> None:
    predicted = _reprolith_curve()
    reference = _REFERENCE["curve"]
    assert len(predicted) == len(reference) == _REFERENCE["steps"] + 1
    # Two independent ODE simulators (COPASI vs libRoadRunner/CVODE) on the same oscillating model.
    peak = max(reference)
    for got, want in zip(predicted, reference):
        assert got == pytest.approx(want, abs=1e-3 * peak)


def test_the_curve_oracle_certifies_it_reproduced() -> None:
    # The shared curve oracle — unchanged from PK/PD — returns a reproduced verdict for this
    # systems-biology model, which is the whole point: the class reuses the contract, it doesn't fork it.
    assessment = judge_curve(
        claim_id="mapk-pp-timecourse",
        quantity="MAPK_PP concentration over time (oscillatory)",
        source_location="BIOMD0000000010; libRoadRunner reference",
        reference=_REFERENCE["curve"],
        predicted=_reprolith_curve(),
    )
    assert assessment.verdict is Verdict.REPRODUCED
