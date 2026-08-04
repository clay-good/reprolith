"""Generic-kinetic class: the curve oracle carries diverse systems-biology models.

Reprolith's third ODE class is generic systems-biology (kinetic) models — the same time-course
reproduction as PK/PD, on biochemical reaction networks rather than compartmental drug models. This
checks the shared simulate + curve oracle on curated, non-PK/PD kinetic models spanning three
network types (signaling, gene-regulatory, metabolic).

Ground truth is an independent simulator: each reference curve in
``datasets/kinetic/cross_validation.json`` was computed by libRoadRunner (CVODE), which shares no
code with the COPASI engine Reprolith runs, so reproducing it is a genuine non-circular cross-tool
check — not COPASI agreeing with itself.

Needs the ``engine`` extra (python-copasi) to run the simulation; skips without it. libRoadRunner is
not needed here — it only generated the committed references.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import (  # noqa: E402
    CurveClaim,
    EnginePin,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    certify_curves,
    judge_curve,
    simulate,
)

_DIR = Path(__file__).parent.parent / "datasets" / "kinetic"
_MODELS = json.loads((_DIR / "cross_validation.json").read_text(encoding="utf-8"))["models"]
_BY_ID = {m["id"]: m for m in _MODELS}


def _reprolith_curve(spec: dict) -> list[float]:
    sbml = (_DIR / f"{spec['id']}.xml").read_text(encoding="utf-8")
    _, values = simulate(sbml, spec["species"], duration=spec["duration"], steps=spec["steps"])
    return list(values)


@pytest.mark.parametrize("model_id", sorted(_BY_ID))
def test_the_curve_oracle_certifies_each_model_reproduced(model_id: str) -> None:
    # The shared curve oracle — unchanged from PK/PD — returns a reproduced verdict against an
    # independent simulator's trajectory for each network type: the class reuses the contract.
    spec = _BY_ID[model_id]
    assessment = judge_curve(
        claim_id=f"{model_id}-timecourse",
        quantity=f"{spec['species']} time-course ({spec['network']})",
        source_location=f"{model_id}; libRoadRunner reference",
        reference=spec["curve"],
        predicted=_reprolith_curve(spec),
    )
    assert assessment.verdict is Verdict.REPRODUCED


@pytest.mark.parametrize("model_id", sorted(_BY_ID))
def test_reproduces_the_independent_trajectory_pointwise(model_id: str) -> None:
    spec = _BY_ID[model_id]
    predicted = _reprolith_curve(spec)
    reference = spec["curve"]
    assert len(predicted) == len(reference) == spec["steps"] + 1
    # Two independent ODE integrators (COPASI vs libRoadRunner/CVODE) on the same network; a small
    # pointwise band absorbs integrator differences and, for oscillators, minor phase drift.
    peak = max(abs(v) for v in reference)
    for got, want in zip(predicted, reference):
        assert got == pytest.approx(want, abs=3e-3 * peak)


def test_certify_curves_assembles_a_reproduced_certificate() -> None:
    # The curve certification entry point (the kinetic analogue of certify_model) runs the model
    # under the pin, judges the trajectory, and builds a scope-flagged certificate — reproduced.
    spec = _BY_ID["BIOMD0000000010"]
    cert = certify_curves(
        (_DIR / f"{spec['id']}.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(title=spec["name"], doi=""),
        engine_pin=EnginePin(engine="copasi", version="test", algorithm="deterministic-lsoda"),
        claims=[CurveClaim(
            claim_id="mapk-pp", quantity="MAPK_PP time-course", species=spec["species"],
            reference=tuple(spec["curve"]), source_location=spec["source"],
            duration=spec["duration"], steps=spec["steps"],
        )],
    )
    assert cert.overall is OverallVerdict.REPRODUCED
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    assert cert.scope.machine  # the inescapable scope flag travels with the certificate
