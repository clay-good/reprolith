#!/usr/bin/env python3
"""Regenerate the generic-kinetic cross-validation reference curve from the committed model.

The kinetic class's ground truth (``datasets/kinetic/mapk_reference_curve.json``) is the species
time-course an independent simulator — libRoadRunner (CVODE) — computes for the committed model.
For a reproducibility tool, that ground truth must itself be reproducible: this regenerates it, so
the committed curve is auditable, not a magic array.

Needs libRoadRunner (``pip install libroadrunner``) — a dev-time reference generator, not a
Reprolith runtime dependency. Deterministic: re-running produces a byte-identical file. Run from
the repo root:

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

MODEL_ID = "BIOMD0000000010"
SPECIES = "MAPK_PP"
DURATION = 4000.0
STEPS = 200


def main() -> None:
    xml = (KIN / f"{MODEL_ID}.xml").read_text(encoding="utf-8")
    runner = roadrunner.RoadRunner(xml)
    runner.timeCourseSelections = ["time", SPECIES]
    result = runner.simulate(0, DURATION, STEPS + 1)
    curve = [round(float(row[1]), 6) for row in result]

    doc = {
        "description": "Independent reference time-course for the Kholodenko2000 MAPK cascade "
                       f"(BioModels {MODEL_ID}), computed by libRoadRunner (CVODE) — a simulator "
                       "with no code shared with the COPASI engine Reprolith runs. Reprolith's "
                       "simulate must reproduce this curve, a non-circular cross-tool check that the "
                       "curve oracle carries a systems-biology kinetic model, not only PK/PD.",
        "model": f"{MODEL_ID} — Kholodenko2000, ultrasensitivity and negative feedback bring "
                 "oscillations in the MAPK cascade",
        "source": f"BioModels https://www.ebi.ac.uk/biomodels/{MODEL_ID} (curated); "
                  "Kholodenko (2000) Eur J Biochem, doi:10.1046/j.1432-1327.2000.01197.x",
        "reference_tool": f"libRoadRunner {roadrunner.__version__} (CVODE)",
        "species": SPECIES,
        "duration": DURATION,
        "steps": STEPS,
        "curve": curve,
    }
    out = KIN / "mapk_reference_curve.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {out.relative_to(REPO)} ({len(curve)} points, peak {max(curve):.4g})")


if __name__ == "__main__":
    main()
