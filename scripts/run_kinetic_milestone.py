#!/usr/bin/env python3
"""Regenerate the generic-kinetic milestone artifact from committed data.

The kinetic counterpart of ``run_milestone.py`` / ``run_fba_milestone.py``. Seeds the catalog with
the curated kinetic entries whose reproducibility is independently known (the cross-validation set),
certifies each *blind* through the shared curve path ``certify_curves`` — the verdict path never
sees the label — scores agreement with ground truth on the same ``run_test_set`` machinery the other
classes use, and writes the walkable result.

Each entry's label is `reproduced`, its ground truth the species time-course an independent simulator
(libRoadRunner) computes for the model; certifying reproduces that curve under Reprolith's COPASI
engine. It also records, per entry, whether the verdict is engine-independent — the same trajectory under
both COPASI and libRoadRunner — so the walkable result shows engine stability alongside blind
agreement. Reproducible from the repository alone — no network — but needs the ``engine`` extra
(python-copasi) and the ``corroborate`` extra (libRoadRunner). Run from the repo root:

    python scripts/run_kinetic_milestone.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from reprolith import (
    Attribution,
    Catalog,
    Claim,
    CurveClaim,
    EnginePin,
    FailureMode,
    Fault,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    certify_curves,
    certify_model,
    corroborate_curve,
    engine_pin,
    run_test_set,
)
from reprolith.certify import _metric
from reprolith.mcp_server import write_json_atomically
from reprolith.persistence import prune_certificate_directory

REPO = Path(__file__).resolve().parents[1]
KIN = REPO / "datasets" / "kinetic"


#: The oscillator this milestone certifies a *period* for, and why this one: its reference curve is
#: sampled 75 times per cycle, so the number is the model's rather than the grid's — which the
#: run's own convergence check confirms rather than assumes. (The repressilator's reference spans
#: 75 cycles at 200 samples, under three per cycle, and a period claim there is the grid's answer.)
_PERIOD_ENTRY = "BIOMD0000000021"


def _period_entry(spec: dict, pin: EnginePin) -> tuple[Identifiers, GroundTruth, object]:
    """Certify the circadian clock's **period and peak-to-trough** against the reference curve's.

    The class's second reproduction target. Five of the six models here oscillate, and the only
    thing this class could certify about any of them was the curve — the one comparison a limit
    cycle punishes, since a curve distance is dominated by phase and phase error accumulates with
    every cycle. A model that reproduces the biology while drifting one percent in period reads as a
    total failure, which is why these papers report a period.

    Non-circular in the same way every other entry here is: both reference values are read off
    **libRoadRunner's** committed trajectory, not off Reprolith's run.
    """
    steps, duration = spec["steps"], spec["duration"]
    times = [duration * i / steps for i in range(steps + 1)]
    cited = (
        f"{spec['source']} — reference period and peak-to-trough read off the curve computed by "
        f"{spec['reference_tool']} re-running this model file, not numbers read from the paper"
    )
    identifiers = Identifiers(
        title=f"{spec['name']} — oscillation period and peak-to-trough",
        accession=f"{spec['id']}_oscillation",
    )
    label = GroundTruth(
        expected=OverallVerdict.REPRODUCED,
        source=f"{spec['source']}; period and peak-to-trough of the {spec['reference_tool']} curve",
    )
    certificate = certify_model(
        (KIN / f"{spec['id']}.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(title=identifiers.title, doi=""),
        engine_pin=pin,
        claims=[
            Claim(
                claim_id=f"{spec['id']}-period",
                quantity=f"oscillation period of {spec['species']} ({spec['network']})",
                species=spec["species"],
                reported=_metric(times, spec["curve"], "period"),
                source_location=cited,
                metric="period",
            ),
            Claim(
                claim_id=f"{spec['id']}-peak-to-trough",
                quantity=f"peak-to-trough height of {spec['species']} ({spec['network']})",
                species=spec["species"],
                reported=_metric(times, spec["curve"], "peak_to_trough"),
                source_location=cited,
                metric="peak_to_trough",
            ),
        ],
        duration=duration,
        steps=steps,
    )
    return identifiers, label, certificate


def main() -> None:
    catalog = Catalog()
    models = json.loads((KIN / "cross_validation.json").read_text(encoding="utf-8"))["models"]
    pin: EnginePin = engine_pin()  # the concrete installed COPASI version

    certified = {}
    for spec in models:
        catalog.add(
            Identifiers(title=spec["name"], accession=spec["id"]),
            ModelClass.KINETIC,
            ground_truth=GroundTruth(
                expected=OverallVerdict.REPRODUCED,
                source=f"{spec['source']}; reference curve via {spec['reference_tool']}",
            ),
        )
        # Certify blind: only the model and the reference curve are inputs, never the label.
        certified[spec["id"]] = certify_curves(
            (KIN / f"{spec['id']}.xml").read_text(encoding="utf-8"),
            paper=PaperIdentity(title=spec["name"], doi=""),
            engine_pin=pin,
            claims=[CurveClaim(
                claim_id=f"{spec['id']}-timecourse",
                quantity=f"{spec['species']} time-course ({spec['network']})",
                species=spec["species"],
                reference=tuple(spec["curve"]),
                source_location=(
                    f"{spec['source']} — reference curve computed by {spec['reference_tool']} "
                    "re-running this model file, not a curve digitized from the paper"
                ),
                duration=spec["duration"],
                steps=spec["steps"],
                # A partial or failed verdict must carry a root cause, and a claim supplying none
                # raises instead of certifying — so this blind run had exactly two outcomes, 6/6 or
                # a traceback, and its published agreement rate was structurally guaranteed rather
                # than measured. The class's own default cause is a reconstruction that does not
                # match the reference trajectory; a matching curve never reads it.
                shortfall=Attribution(
                    mode=FailureMode.UNCATEGORIZED,
                    implicated=spec["species"],
                    fault=Fault.RECONSTRUCTION,
                ),
            )],
        )

    oscillator = next(spec for spec in models if spec["id"] == _PERIOD_ENTRY)
    identifiers, label, certificate = _period_entry(oscillator, pin)
    catalog.add(identifiers, ModelClass.KINETIC, ground_truth=label)
    certified[identifiers.accession] = certificate

    certificates, report = run_test_set(
        catalog.entries, engine_pin=pin, certified=certified, advance=True
    )

    milestone = KIN / "milestone"
    milestone.mkdir(exist_ok=True)
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    certs = milestone / "certificates"
    certs.mkdir(exist_ok=True)
    prune_certificate_directory(certs, certified)
    for accession, cert in certified.items():
        (certs / f"{accession}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    # Atomic: this file is what both surfaces read at start-up and what a live MCP server
    # re-reads under its lock, and a plain write_text truncates it to zero before writing
    # ~52 KB. A crash in that window leaves a blank catalog behind.
    write_json_atomically(milestone / "catalog.json", catalog.to_dict())

    # Engine independence: the same curve under both COPASI and libRoadRunner (spec:
    # simulation-oracle). Recorded alongside the blind agreement so the walkable result shows no
    # verdict here rests on a single solver.
    corroboration = {}
    for spec in models:
        result = corroborate_curve(
            (KIN / f"{spec['id']}.xml").read_text(encoding="utf-8"),
            spec["species"], duration=spec["duration"], steps=spec["steps"],
        )
        # `record()` carries the fields every class's record shares — the engines, the builds
        # they ran as, and the distance as a *bound* rather than a measurement (COPASI is not
        # bit-identical across repeated calls, and five figures of it were not regenerable on the
        # same machine). Assembled by hand here and in the PK/PD script, they drifted.
        corroboration[spec["id"]] = result.record()
    (milestone / "corroboration.json").write_text(
        json.dumps(corroboration, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    stable = sum(1 for c in corroboration.values() if c["engine_independent"])
    print(f"engine-independent: {stable}/{len(corroboration)}")
    counts = Counter(cert.overall.value for cert in certificates)
    print(f"entries: {len(certificates)} | verdicts: {dict(counts)}")
    print(f"agreement: {report.agreements}/{report.total}")
    print(f"wrote {(milestone / 'agreement_report.json').relative_to(REPO)}")


if __name__ == "__main__":
    main()
