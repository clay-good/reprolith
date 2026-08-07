#!/usr/bin/env python3
"""Regenerate the stochastic (SSA) milestone artifact from closed-form ground truth.

The stochastic counterpart of the other classes' milestone scripts. Seeds the catalog with reaction
networks whose stationary/equilibrium mean is known in closed form, certifies each *blind* through
`certify_stochastic` — the verdict path never sees the label — and scores agreement on the same
`run_test_set` machinery. The ground truth is analytical (Poisson and binomial means), so it needs
no external tool and no network; the pinned seed makes every certificate byte-reproducible.

Run from the repo root:  python scripts/run_stochastic_milestone.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from reprolith import (
    Catalog,
    EnginePin,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    Reaction,
    RunMetadata,
    StochasticClaim,
    certificate_digest,
    certify_stochastic,
    render_human,
    run_test_set,
)

REPO = Path(__file__).resolve().parents[1]
STO = REPO / "datasets" / "stochastic"


def _immigration_death(k: float, gamma: float) -> list[Reaction]:
    return [Reaction(k, (), ((0, 1),)), Reaction(gamma, ((0, 1),), ())]


def _reversible(kf: float, kr: float) -> list[Reaction]:
    return [Reaction(kf, ((0, 1),), ((1, 1),)), Reaction(kr, ((1, 1),), ((0, 1),))]


# Each system: its network, initial state, and the claim whose reported value is the closed-form
# mean — Poisson mean k/γ for immigration-death, binomial mean N·kf/(kf+kr) for the reversible one.
_SYSTEMS = {
    "immigration_death_10": {
        "title": "Immigration-death process (k=10, γ=1) — Poisson stationary mean",
        "n_species": 1, "reactions": _immigration_death(10.0, 1.0), "initial": [0],
        "species": 0, "reported_mean": 10.0, "duration": 40.0, "trajectories": 400, "seed": 20260807,
    },
    "immigration_death_4": {
        "title": "Immigration-death process (k=6, γ=1.5) — Poisson stationary mean",
        "n_species": 1, "reactions": _immigration_death(6.0, 1.5), "initial": [0],
        "species": 0, "reported_mean": 4.0, "duration": 40.0, "trajectories": 400, "seed": 11,
    },
    "reversible_isomerization": {
        "title": "Reversible isomerization A<->B (N=50, kf=3, kr=1) — binomial equilibrium mean",
        "n_species": 2, "reactions": _reversible(3.0, 1.0), "initial": [50, 0],
        "species": 1, "reported_mean": 37.5, "duration": 30.0, "trajectories": 400, "seed": 1234,
    },
}


def main() -> None:
    pin = EnginePin(engine="reprolith-ssa", version="0.0.1")
    catalog = Catalog()
    certified = {}

    for key in sorted(_SYSTEMS):
        s = _SYSTEMS[key]
        catalog.add(
            Identifiers(title=s["title"], accession=key),
            ModelClass.STOCHASTIC,
            ground_truth=GroundTruth(
                expected=OverallVerdict.PARTIALLY_REPRODUCED,  # qualified by sampling -> never clean
                source=f"closed-form mean {s['reported_mean']}",
            ),
        )
        certified[key] = certify_stochastic(
            paper=PaperIdentity(title=s["title"], doi=""),
            engine_pin=pin,
            n_species=s["n_species"], reactions=s["reactions"], initial=s["initial"],
            claims=[StochasticClaim(
                claim_id=f"{key}-mean", quantity="mean copy number", species=s["species"],
                reported_mean=s["reported_mean"], source_location="closed-form",
                duration=s["duration"], trajectories=s["trajectories"], seed=s["seed"],
            )],
        )

    certificates, report = run_test_set(catalog.entries, engine_pin=pin, certified=certified, advance=True)

    milestone = STO / "milestone"
    (milestone / "certificates").mkdir(parents=True, exist_ok=True)
    run = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="stochastic-milestone", tool_version="0.0.1")
    for key, cert in certified.items():
        (milestone / "certificates" / f"{key}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (milestone / "certificates" / f"{key}.txt").write_text(render_human(cert, run), encoding="utf-8")
    (milestone / "catalog.json").write_text(
        json.dumps(catalog.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"stochastic milestone: {report.agreements}/{report.total} agree with ground truth")
    print(f"verdicts: {dict(counts)}")
    print(f"digests: {[certificate_digest(c) for c in certificates]}")


if __name__ == "__main__":
    main()
