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
from collections import Counter
from pathlib import Path

from reprolith import (
    Catalog,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    RunMetadata,
    SpatialClaim,
    certificate_digest,
    certify_spatial,
    gaussian_profile,
    render_human,
    run_test_set,
)
from reprolith.corroboration import corroborate_profile
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
            # `partially-reproduced`, not `reproduced`: the profile matches the closed form
            # exactly, and the certificate is still downgraded because this class runs every claim
            # under a zero-flux boundary Reprolith imposes and the paper did not state — the same
            # load-bearing qualification the stochastic class carries for its ensemble. The label
            # states what an honest verdict here looks like, so a run that dropped the
            # qualification would show up as a disagreement rather than as a better number.
            ground_truth=GroundTruth(
                expected=OverallVerdict.PARTIALLY_REPRODUCED,
                source="closed-form Gaussian diffusion (under Reprolith's own boundary condition)",
            ),
        )
        certified[key] = certify_spatial(
            paper=PaperIdentity(title=s["title"], doi=""),
            engine_pin=pin,
            claims=[SpatialClaim(
                claim_id=f"{key}-profile", quantity="diffused concentration profile",
                initial=initial, reference=reference, source_location="closed-form",
                diffusivity=s["D"], dx=_DX, dt=dt, steps=s["steps"],
            )],
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


if __name__ == "__main__":
    main()
