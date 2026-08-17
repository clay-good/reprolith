"""Every class front-end can publish a shortfall, not only a pass (spec: simulation-oracle 4.4).

The oracle refuses a bare non-pass: a partial or failed verdict must carry a root cause. The
front-ends, though, took that root cause only from the caller, and the callers that matter — the
milestone scripts and `Claim.from_record`, which does not parse a shortfall at all — supply none.
So a claim that genuinely missed raised instead of certifying, and the only two outcomes a run
could have were a clean pass and a traceback: the agreement rates those runs published were
guaranteed rather than measured.

These tests hold the other outcome open. Each one perturbs a *correct* reproduction until it is
wrong and asserts the certificate says so, with a cause attached.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest
from reprolith import (
    DossierClaim,
    EnginePin,
    ModelArtifact,
    OverallVerdict,
    PaperIdentity,
    ReferenceKind,
    SpatialClaim,
    Verdict,
    certify_constraint_based,
    certify_spatial,
    constraint_based_dossier,
    gaussian_profile,
)
from reprolith.spatial import solver_pin as spatial_pin

_CB = Path(__file__).parent.parent / "datasets" / "constraint_based"

# The milestone's own discretization, so what is measured here is the published configuration.
_N, _L = 201, 20.0
_DX = 2 * _L / (_N - 1)
_CENTERS = tuple(-_L + i * _DX for i in range(_N))


def _spatial_certificate(reference_variance: float) -> tuple[OverallVerdict, Verdict, str | None]:
    """Certify the milestone's D=1 diffusion against a reference of the given final variance."""
    steps, diffusivity, var0 = 500, 1.0, 1.0
    dt = 0.4 * _DX * _DX / diffusivity
    cert = certify_spatial(
        paper=PaperIdentity(title="1-D diffusion of a Gaussian", doi=""),
        engine_pin=spatial_pin(),
        claims=[
            SpatialClaim(
                claim_id="profile", quantity="diffused concentration profile",
                initial=tuple(gaussian_profile(_CENTERS, mass=10.0, variance=var0)),
                reference=tuple(gaussian_profile(_CENTERS, mass=10.0, variance=reference_variance)),
                source_location="closed-form", diffusivity=diffusivity,
                dx=_DX, dt=dt, steps=steps,
            )
        ],
    )
    assessment = cert.assessments[0]
    return cert.overall, assessment.verdict, assessment.root_cause


def test_the_spatial_class_reproduces_the_closed_form_it_is_validated_against() -> None:
    exact = 1.0 + 2 * 1.0 * (500 * 0.4 * _DX * _DX)  # var0 + 2·D·t
    overall, verdict, root_cause = _spatial_certificate(exact)
    assert (overall, verdict, root_cause) == (OverallVerdict.REPRODUCED, Verdict.REPRODUCED, None)


def test_a_spatial_profile_that_misses_is_published_rather_than_raised() -> None:
    # Twice the diffused variance: a solver this wrong must be able to produce a certificate that
    # says so. Before the front-end carried a default cause, this raised.
    exact = 1.0 + 2 * 1.0 * (500 * 0.4 * _DX * _DX)
    overall, verdict, root_cause = _spatial_certificate(exact * 2)
    assert overall is OverallVerdict.NOT_REPRODUCED
    assert verdict in (Verdict.PARTIAL, Verdict.FAILED)
    assert root_cause == "uncategorized"  # undetermined, and recorded as undetermined


def _constraint_based_certificate(reported_growth: float) -> tuple[OverallVerdict, Verdict, str | None]:
    """Certify the committed iNF517 genome-scale model against a stated growth rate."""
    model_id = "iNF517"
    dossier = constraint_based_dossier(
        model_id,
        model=ModelArtifact(
            filename=f"{model_id}.xml.gz", detected_format="sbml-fbc", validates=True
        ),
        objective_claims=[
            DossierClaim(
                id=f"{model_id}-growth", quantity="maximal growth rate on the distributed medium",
                conditions="the model's distributed exchange bounds",
                source_location="BiGG", reference_kind=ReferenceKind.NUMERIC,
                reference_data=(reported_growth,),
            )
        ],
        medium=(),
    )
    sbml = gzip.decompress(
        (_CB / "cross_validation" / f"{model_id}.xml.gz").read_bytes()
    ).decode("utf-8")
    cert = certify_constraint_based(
        dossier, sbml=sbml,
        paper=PaperIdentity(title="A genome-scale reconstruction", doi=""),
        engine_pin=EnginePin(engine="test-lp", version="0.0.0"),
    )
    assessment = cert.assessments[0]
    return cert.overall, assessment.verdict, assessment.root_cause


# The constraint-based half needs the LP backend; the spatial half above is dependency-free.
_needs_lp = pytest.mark.skipif(
    importlib.util.find_spec("scipy") is None,
    reason="the constraint-based oracle needs the 'fba' extra (scipy)",
)


@_needs_lp
def test_the_constraint_based_class_reproduces_its_reference_growth() -> None:
    reference = json.loads(
        (_CB / "cross_validation" / "reference_growth.json").read_text(encoding="utf-8")
    )["models"]["iNF517"]["reference_growth"]
    overall, verdict, root_cause = _constraint_based_certificate(reference)
    assert (overall, verdict, root_cause) == (OverallVerdict.REPRODUCED, Verdict.REPRODUCED, None)


@_needs_lp
def test_a_constraint_based_objective_that_misses_is_published_rather_than_raised() -> None:
    # A growth rate overstated by 20% — the class's own first-named failure mode is a mis-stated
    # medium, which shows up exactly like this. The certificate has to be able to say so.
    reference = json.loads(
        (_CB / "cross_validation" / "reference_growth.json").read_text(encoding="utf-8")
    )["models"]["iNF517"]["reference_growth"]
    overall, verdict, root_cause = _constraint_based_certificate(reference * 1.20)
    assert overall is OverallVerdict.NOT_REPRODUCED
    assert verdict in (Verdict.PARTIAL, Verdict.FAILED)
    assert root_cause == "uncategorized"


def test_a_curve_and_a_scalar_claim_that_miss_are_published_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PK/PD and kinetic front-ends, with the engine stubbed out.

    `certify_model` and `certify_curves` run under the engine extra, which the dependency-free
    gate does not install — but the wiring under test is which attribution reaches the judge, not
    what the simulator returns. So the simulator is replaced by a fixed, obviously-wrong time
    course: the claims miss, and the certificates have to say so. `Claim.from_record` never parses
    a shortfall, so this is exactly what the blind PK/PD set would hit on a real miss.
    """
    import reprolith.certify as certify_module
    from reprolith import Claim, CurveClaim, certify_curves, certify_model

    times = tuple(i / 10.0 for i in range(11))
    monkeypatch.setattr(
        certify_module, "simulate", lambda *a, **k: (times, tuple(10.0 for _ in times))
    )
    paper = PaperIdentity(title="A paper whose numbers do not come back", doi="10.0/miss")
    pin = EnginePin(engine="test-engine", version="0.0.0")

    scalar = certify_model(
        "<sbml/>", paper=paper, engine_pin=pin, duration=1.0, steps=10,
        claims=[Claim(claim_id="cmax", quantity="plasma Cmax", species="C", reported=40.0,
                      source_location="Table 1")],
    )
    assert scalar.overall is OverallVerdict.NOT_REPRODUCED
    assert scalar.assessments[0].root_cause == "uncategorized"
    assert scalar.assessments[0].fault_hypothesis == "reconstruction"  # never a bare accusation

    curve = certify_curves(
        "<sbml/>", paper=paper, engine_pin=pin,
        claims=[CurveClaim(claim_id="course", quantity="plasma concentration", species="C",
                           reference=tuple(40.0 - 3.0 * t for t in times),
                           source_location="Fig 1", duration=1.0, steps=10)],
    )
    assert curve.overall is OverallVerdict.NOT_REPRODUCED
    assert curve.assessments[0].root_cause == "uncategorized"
