#!/usr/bin/env python3
"""Regenerate the spatial (reaction-diffusion) milestone artifact from closed-form ground truth.

The spatial counterpart of the other classes' milestone scripts. Seeds the catalog with 1-D
diffusion systems whose profile is known in closed form (a Gaussian whose variance grows by 2·D·t),
certifies each *blind* through `certify_spatial` — the verdict path never sees the label — and scores
agreement on the same `run_test_set` machinery. The ground truth is analytical, so it needs no
external tool and no network, and the pinned discretization makes every certificate byte-reproducible.

It also re-solves each profile under scipy's LSODA by method of lines and writes
`corroboration.json` beside the certificates. That half needs scipy (the fba or corroborate extra).

Run from the repo root:  python scripts/run_spatial_milestone.py
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from reprolith import (
    UNBOUNDED,
    Catalog,
    FrontSpeedClaim,
    GradientClaim,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    RunMetadata,
    SpatialClaim,
    Tolerance,
    ToleranceSource,
    certificate_digest,
    certify_spatial,
    gaussian_profile,
    render_human,
    run_test_set,
)
from reprolith.corroboration import (
    corroborate_front_speed,
    corroborate_gradient_length,
    corroborate_profile,
)
from reprolith.mcp_server import write_json_atomically
from reprolith.persistence import prune_certificate_directory
from reprolith.spatial import solver_pin

REPO = Path(__file__).resolve().parents[1]
SPA = REPO / "datasets" / "spatial"

_L, _N = 20.0, 201
_DX = 2 * _L / (_N - 1)
_CENTERS = tuple(-_L + i * _DX for i in range(_N))

# Each system: diffusivity, initial variance, total mass, and step count. The reported profile is the
# exact analytical Gaussian at the elapsed time — the closed-form ground truth.
#: The explicit scheme is stable to 0.5; the milestone runs at less than half of that so a
#: perturbed diffusivity still runs and can be judged instead of refused.
_DIFFUSION_NUMBER = 0.2

_SYSTEMS = {
    "diffusion_D1": {"title": "1-D diffusion of a Gaussian (D=1)", "D": 1.0, "var0": 1.0, "mass": 10.0, "steps": 1000},
    "diffusion_D2": {"title": "1-D diffusion of a Gaussian (D=2)", "D": 2.0, "var0": 1.5, "mass": 7.0, "steps": 800},
    "diffusion_Dhalf": {"title": "1-D diffusion of a Gaussian (D=0.5)", "D": 0.5, "var0": 2.0, "mass": 5.0, "steps": 1200},
}


#: The two **scalars** this class certifies, beside the three profiles. They are here for a reason
#: the profiles cannot serve: a decay length and a front speed are numbers a paper prints in its
#: text, so unlike a profile they are reachable without a curator digitizing a figure — and the
#: README says so, while the blind evidence covered profiles alone. They also make this the one
#: milestone whose entries do not all carry the same expected verdict: a gradient's walls are the
#: model rather than a choice this engine made, so its certificate can and does read a clean
#: `reproduced`, and a run that started qualifying it would show up here as a disagreement.
#:
#: The wavelength claim is deliberately **not** here, and the reason is worth stating: linear
#: stability predicts the mode that grows fastest, and the saturated nonlinear pattern selects a
#: different one (21 against 20 on the configuration this class self-validates). So there is no
#: independent closed form for the quantity the certificate judges, and a blind entry would either
#: score the class against the wrong number or check the solver against itself. It is not
#: unchecked: `corroborate_pattern_wavelength` re-runs it under scipy's LSODA and both engines
#: select mode 20 (`tests/test_spatial_corroboration.py`). That is a second *integrator* and not a
#: second ground truth — they share this grid and this stencil — which is why it corroborates the
#: claim without qualifying as the blind reference an entry here would need.
_GRADIENT_D, _GRADIENT_K, _GRADIENT_SOURCE = 1.0, 0.25, 100.0
_GRADIENT_DX = 0.1
_FRONT_D, _FRONT_R = 1.0, 1.0
_FRONT_DX = 0.5

#: The bias is measured, so the override is principled rather than a magic number — and what it is
#: *for* was corrected once: this said the deficit was the front's logarithmic approach to its
#: asymptote, and refining the time step shows it is mostly the explicit stepper (4.2% at a
#: diffusion number of 0.2, 1.9% at 0.1, 0.7% at 0.05). `tests/test_spatial_front_claim.py` uses
#: the same tolerance.
_FRONT_TOLERANCE = Tolerance(
    0.10, 0.20, ToleranceSource.REVIEWER_OVERRIDE,
    rationale="the measured speed sits below 2*sqrt(rD) by the explicit stepper's O(dt) time error (4.2% at a diffusion number of 0.2, 1.9% at 0.1, 0.7% at 0.05) plus the KPP front's logarithmic finite-time approach; 10% covers both",
)


def _gradient_entry() -> tuple[Identifiers, GroundTruth, list[GradientClaim]]:
    """A morphogen gradient's decay length against the closed form `λ = √(D/k)`."""
    dt = _DIFFUSION_NUMBER * _GRADIENT_DX * _GRADIENT_DX / _GRADIENT_D
    claim = GradientClaim(
        claim_id="gradient-decay-length", quantity="morphogen decay length",
        reported=math.sqrt(_GRADIENT_D / _GRADIENT_K), source_location="closed-form",
        source=_GRADIENT_SOURCE, diffusivity=_GRADIENT_D, decay=_GRADIENT_K,
        dx=_GRADIENT_DX, points=300, dt=dt, steps=40000, fit_from=20, fit_to=120,
    )
    return (
        Identifiers(title="Morphogen gradient decay length (D=1, k=0.25)", accession="gradient_length"),
        GroundTruth(
            expected=OverallVerdict.REPRODUCED,
            source="closed-form exponential gradient, lambda = sqrt(D/k) = 2.0",
        ),
        [claim],
    )


def _front_entry() -> tuple[Identifiers, GroundTruth, list[FrontSpeedClaim]]:
    """A Fisher-KPP invasion front's speed against the closed form `c = 2√(rD)`."""
    dt = _DIFFUSION_NUMBER * _FRONT_DX * _FRONT_DX / _FRONT_D
    window = round(100.0 / dt)
    points = 1201  # [0, 600]: long enough that the front never reaches the wall
    claim = FrontSpeedClaim(
        claim_id="front-speed", quantity="Fisher-KPP asymptotic front speed",
        reported=2.0 * math.sqrt(_FRONT_R * _FRONT_D), source_location="closed-form",
        initial=tuple(1.0 if i * _FRONT_DX < 20.0 else 0.0 for i in range(points)),
        diffusivity=_FRONT_D, growth=_FRONT_R, dx=_FRONT_DX, dt=dt,
        settle_steps=window, measure_steps=window, tolerance=_FRONT_TOLERANCE,
    )
    return (
        Identifiers(title="Fisher-KPP invasion front speed (D=1, r=1)", accession="front_speed"),
        GroundTruth(
            expected=OverallVerdict.REPRODUCED,
            source="closed-form pulled-front speed, c = 2*sqrt(rD) = 2.0, judged under a stated "
                   "10% tolerance for the explicit stepper's O(dt) error and the front's "
                   "finite-time approach",
        ),
        [claim],
    )


def main() -> None:
    # Names the finite-difference solver's own revision, so a change to it re-opens these
    # certificates for review instead of leaving them looking fresh under an unmoving version.
    pin = solver_pin()
    catalog = Catalog()
    certified = {}

    for key in sorted(_SYSTEMS):
        s = _SYSTEMS[key]
        # The diffusion number is 0.2, not the 0.4 this used to run at, and the step count doubles
        # to keep the elapsed time — and so the physical scenario — the same. At 0.4 the published
        # configuration sat so near the explicit scheme's 0.5 limit that a diffusivity only 25% too
        # large was *refused as an unstable discretization* rather than judged, so the one quantity
        # this class exists to reproduce could not be got wrong loudly enough to be published as a
        # failure. With headroom, a wrong D produces a verdict.
        dt = _DIFFUSION_NUMBER * _DX * _DX / s["D"]
        elapsed = s["steps"] * dt
        initial = tuple(gaussian_profile(_CENTERS, mass=s["mass"], variance=s["var0"]))
        reference = tuple(gaussian_profile(_CENTERS, mass=s["mass"], variance=s["var0"] + 2 * s["D"] * elapsed))
        catalog.add(
            Identifiers(title=s["title"], accession=key),
            ModelClass.SPATIAL,
            # `reproduced`, and it reads that way for a reason worth stating, because it read
            # `partially-reproduced` for a month: the reference is the free-space Gaussian, which
            # is the solution on a domain with no walls at all. So these claims *state* their
            # domain — `boundary=UNBOUNDED` below — and the qualification they used to carry, for
            # a zero-flux wall Reprolith imposed and the paper did not state, is not a caveat any
            # more but a question the run answers: on this grid the two edge rules bracket the
            # free-space solution and their profiles differ by ~1e-6, three orders below the
            # tenth-of-tolerance budget. A wall that cannot be detected is not an assumption.
            # Judged blind, so a run that could no longer show that would fail this entry rather
            # than quietly publishing a clean pass.
            ground_truth=GroundTruth(
                expected=OverallVerdict.REPRODUCED,
                source="closed-form Gaussian diffusion (free space; the finite grid's walls are measured not to reach the profile)",
            ),
        )
        certified[key] = certify_spatial(
            paper=PaperIdentity(title=s["title"], doi=""),
            engine_pin=pin,
            claims=[SpatialClaim(
                claim_id=f"{key}-profile", quantity="diffused concentration profile",
                initial=initial, reference=reference, source_location="closed-form",
                diffusivity=s["D"], dx=_DX, dt=dt, steps=s["steps"], boundary=UNBOUNDED,
            )],
        )

    for identifiers, truth, claims in (_gradient_entry(), _front_entry()):
        catalog.add(identifiers, ModelClass.SPATIAL, ground_truth=truth)
        # Certified blind like the profiles: the verdict path never sees the label. Routed by
        # claim type rather than by a flag — `certify_spatial` takes each kind in its own argument.
        certified[str(identifiers.accession)] = certify_spatial(
            paper=PaperIdentity(title=identifiers.title, doi=""),
            engine_pin=pin,
            gradients=[c for c in claims if isinstance(c, GradientClaim)],
            fronts=[c for c in claims if isinstance(c, FrontSpeedClaim)],
        )

    certificates, report = run_test_set(catalog.entries, engine_pin=pin, certified=certified, advance=True)

    # The same three profiles re-solved under scipy's LSODA by method of lines — an adaptive
    # implicit integrator against this class's fixed-step explicit one. Reported beside the
    # certificates, never gating them. What it separates is the time integration; both sides use
    # the same second-order stencil, which `corroborate_profile` says up front.
    corroboration = {}
    for key in sorted(_SYSTEMS):
        s = _SYSTEMS[key]
        dt = _DIFFUSION_NUMBER * _DX * _DX / s["D"]
        corroboration[key] = corroborate_profile(
            gaussian_profile(_CENTERS, mass=s["mass"], variance=s["var0"]),
            diffusivity=s["D"], dx=_DX, dt=dt, steps=s["steps"],
        ).record()

    # The two scalars, re-solved under the same second engine. They had no corroboration at all
    # when they landed — `corroborate_profile` re-solves a profile, and a decay length is read
    # *off* a run rather than being one — and every surface said so. What closing it turned up is
    # in the front's record: the two engines disagree about the speed by 4.7%, which is published
    # as a disagreement rather than widened away.
    gradient_dt = _DIFFUSION_NUMBER * _GRADIENT_DX * _GRADIENT_DX / _GRADIENT_D
    corroboration["gradient_length"] = corroborate_gradient_length(
        source=_GRADIENT_SOURCE, diffusivity=_GRADIENT_D, decay=_GRADIENT_K,
        dx=_GRADIENT_DX, points=300, dt=gradient_dt, steps=40000, fit_from=20, fit_to=120,
    ).record()
    front_dt = _DIFFUSION_NUMBER * _FRONT_DX * _FRONT_DX / _FRONT_D
    front_window = round(100.0 / front_dt)
    corroboration["front_speed"] = corroborate_front_speed(
        initial=tuple(1.0 if i * _FRONT_DX < 20.0 else 0.0 for i in range(1201)),
        diffusivity=_FRONT_D, growth=_FRONT_R, dx=_FRONT_DX, dt=front_dt,
        settle_steps=front_window, measure_steps=front_window,
    ).record()

    milestone = SPA / "milestone"
    (milestone / "certificates").mkdir(parents=True, exist_ok=True)
    prune_certificate_directory(milestone / "certificates", certified)
    run = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="spatial-milestone", tool_version="0.0.1")
    for key, cert in certified.items():
        (milestone / "certificates" / f"{key}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (milestone / "certificates" / f"{key}.txt").write_text(render_human(cert, run), encoding="utf-8")
    # Atomic: this file is what both surfaces read at start-up and what a live MCP server
    # re-reads under its lock, and a plain write_text truncates it to zero before writing
    # ~52 KB. A crash in that window leaves a blank catalog behind.
    write_json_atomically(milestone / "catalog.json", catalog.to_dict())
    (milestone / "corroboration.json").write_text(
        json.dumps(corroboration, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"spatial milestone: {report.agreements}/{report.total} agree with ground truth")
    print(f"verdicts: {dict(counts)}")
    print(f"digests: {[certificate_digest(c) for c in certificates]}")
    agreed = sum(1 for row in corroboration.values() if row["engine_independent"])
    print(f"corroboration: {agreed}/{len(corroboration)} engine-independent vs scipy's LSODA")
    for key in sorted(corroboration):
        if not corroboration[key]["engine_independent"]:
            print(f"  {key}: the two engines disagree by more than the criterion — published as a "
                  "disagreement, which is what this comparison is for")


if __name__ == "__main__":
    main()
