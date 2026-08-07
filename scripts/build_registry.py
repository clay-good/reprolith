#!/usr/bin/env python3
"""Build the public reproduction registry from every class's committed milestone certificates.

Aggregates the walkable milestone certificates of all four model classes — PK/PD, constraint-based,
kinetic, and logical — into one browsable HTML page via `reprolith.render_registry` (spec:
certificate-publication, "Every certificate is publicly browsable"). Reads only committed JSON, so
it needs no extras and no network. Writes `datasets/registry.html`. Run from the repo root:

    python scripts/build_registry.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import certificate_from_content, render_registry

REPO = Path(__file__).resolve().parents[1]

# Each class's milestone certificate directory and the model-class label it certifies.
_SOURCES = {
    "ode-pkpd": REPO / "datasets" / "milestone" / "certificates",
    "constraint-based": REPO / "datasets" / "constraint_based" / "milestone" / "certificates",
    "kinetic": REPO / "datasets" / "kinetic" / "milestone" / "certificates",
    "logical": REPO / "datasets" / "logical" / "milestone" / "certificates",
    "stochastic": REPO / "datasets" / "stochastic" / "milestone" / "certificates",
    "spatial": REPO / "datasets" / "spatial" / "milestone" / "certificates",
}


def collect() -> list[tuple[str, object]]:
    entries: list[tuple[str, object]] = []
    for model_class, directory in _SOURCES.items():
        for path in sorted(directory.glob("*.json")):
            content = json.loads(path.read_text(encoding="utf-8"))
            entries.append((model_class, certificate_from_content(content)))
    return entries


def main() -> None:
    entries = collect()
    html = render_registry(entries)
    out = REPO / "datasets" / "registry.html"
    out.write_text(html, encoding="utf-8")
    by_class: dict[str, int] = {}
    for model_class, _ in entries:
        by_class[model_class] = by_class.get(model_class, 0) + 1
    print(f"wrote {out} — {len(entries)} certificates: {by_class}")


if __name__ == "__main__":
    main()
