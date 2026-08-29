#!/usr/bin/env python3
"""Regenerate the generic-kinetic cross-validation reference curves from the committed models.

The kinetic class's ground truth (``datasets/kinetic/cross_validation.json``) is the species
time-course an independent simulator — libRoadRunner (CVODE) — computes for each committed model.
For a reproducibility tool, that ground truth must itself be reproducible: this regenerates every
reference curve from its model, so the committed arrays are auditable, not magic numbers.

The per-model settings (species, duration, steps) are read from the existing manifest, so this
recomputes the curves in place without changing the set. Needs libRoadRunner
(``pip install libroadrunner``) — a dev-time reference generator, not a Reprolith runtime
dependency. Deterministic: re-running produces a byte-identical file. Run from the repo root:

    python scripts/regenerate_kinetic_references.py
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import roadrunner

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
KIN = REPO / "datasets" / "kinetic"
MANIFEST = KIN / "cross_validation.json"


def main() -> None:
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for spec in doc["models"]:
        xml = (KIN / f"{spec['id']}.xml").read_text(encoding="utf-8")
        runner = roadrunner.RoadRunner(xml)
        # The concentration, matching what COPASI's getConcentrationData returns on the other side
        # of the comparison. A bare species id here is the amount, which differs by the compartment
        # volume — identical only because every committed model has size 1.
        runner.timeCourseSelections = ["time", f"[{spec['species']}]"]
        result = runner.simulate(0, spec["duration"], spec["steps"] + 1)
        spec["curve"] = [round(float(row[1]), 6) for row in result]
        spec["reference_tool"] = f"libRoadRunner {roadrunner.__version__} (CVODE)"
        print(f"  {spec['id']} {spec['species']}: {len(spec['curve'])} points, peak {max(spec['curve']):.4g}")
    MANIFEST.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO)}")


if __name__ == "__main__":
    main()
