#!/usr/bin/env python3
"""Export the metformin worked example's reconstruction as a COMBINE archive.

The worked example ships the model and the rendered certificate. What it did not ship was the
reconstruction in a form anything but Reprolith can run: the window, the sample count, the output
read, and — the half that matters — the 779.9 mg free-base dose that separates the 1000 mg claim
from the 500 mg one. This writes all of it as `metformin_reconstruction.omex`, from the committed
bundle and the committed model, so a stranger can open the published reproduction in any SED-ML
tool (spec: ``certificate-publication`` — a reconstruction ships in the standard runnable form).

The bytes are deterministic, so the committed archive is checkable rather than merely present:
``tests/test_export.py`` regenerates it and compares. Reproducible from the repository alone — no
network, and no optional extra. Run from the repo root:

    python scripts/export_worked_example_archive.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import build_bundle_sedml, build_omex_archive, bundle_from_dict

ROOT = Path(__file__).parent.parent
BUNDLE = ROOT / "datasets" / "milestone" / "bundles" / "BIOMD0000001028.json"
MODEL = ROOT / "datasets" / "worked_examples" / "Zake2021_metformin_human_single_PO.xml"
ARCHIVE = ROOT / "datasets" / "worked_examples" / "metformin_reconstruction.omex"

#: The model's name inside the archive, kept as the file the worked example already publishes so
#: the archive and the loose file are visibly the same artifact.
MODEL_LOCATION = "Zake2021_metformin_human_single_PO.xml"


def export() -> tuple[bytes, tuple[str, ...], tuple[str, ...]]:
    """The archive bytes, the claims it expresses, and the recipe steps it could not."""
    bundle = bundle_from_dict(json.loads(BUNDLE.read_text(encoding="utf-8")))
    model = MODEL.read_text(encoding="utf-8")
    experiment = build_bundle_sedml(bundle, model, model_location=MODEL_LOCATION)
    archive = build_omex_archive(model, experiment.sedml, model_location=MODEL_LOCATION)
    return archive, experiment.expressed, experiment.unexpressed


def main() -> None:
    archive, expressed, unexpressed = export()
    ARCHIVE.write_bytes(archive)
    print(f"wrote {ARCHIVE.relative_to(ROOT)} ({len(archive)} bytes)")
    print(f"  claims expressed: {', '.join(expressed)}")
    for line in unexpressed:
        print(f"  not expressed: {line}")


if __name__ == "__main__":
    main()
