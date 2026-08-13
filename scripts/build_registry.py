#!/usr/bin/env python3
"""Build the public reproduction registry from every class's committed milestone certificates.

Aggregates the walkable milestone certificates of all six model classes — PK/PD, constraint-based,
kinetic, logical, stochastic, and spatial — into one browsable HTML page via
`reprolith.render_registry` (spec: certificate-publication, "Every certificate is publicly
browsable"), with a blind self-validation summary banner. Reads only committed JSON, so it needs no
extras and no network. Writes `datasets/registry.html`. Run from the repo root:

    python scripts/build_registry.py
"""

from __future__ import annotations

import json

from reprolith import certificate_from_content, render_registry
from reprolith.mcp_server import milestone_agreement_reports, milestone_certificate_dirs
from reprolith.query import self_validation_summary

# Each class's milestone certificate directory and the model-class label it certifies — the same
# source of truth the read surfaces aggregate into the query ledger, so the registry and the
# queryable surface can never list a different set of certificates. Read and write both hang off
# this one root (the imported package's datasets dir), so the registry can't be built from one
# checkout's certificates and written into another's.
_SOURCES = milestone_certificate_dirs()
_DATASETS = _SOURCES["ode-pkpd"].parents[1]  # .../datasets


def collect() -> list[tuple[str, object]]:
    entries: list[tuple[str, object]] = []
    for model_class, directory in _SOURCES.items():
        for path in sorted(directory.glob("*.json")):
            content = json.loads(path.read_text(encoding="utf-8"))
            entries.append((model_class, certificate_from_content(content)))
    return entries


def main() -> None:
    entries = collect()
    # The blind self-validation track record, built from the same committed agreement reports the
    # CLI/MCP surfaces summarize (no certificate ledger to load), so the browsable registry's
    # credibility summary can't diverge from the queried one.
    self_validation = self_validation_summary(milestone_agreement_reports())
    html = render_registry(entries, self_validation=self_validation)
    out = _DATASETS / "registry.html"
    out.write_text(html, encoding="utf-8")
    by_class: dict[str, int] = {}
    for model_class, _ in entries:
        by_class[model_class] = by_class.get(model_class, 0) + 1
    print(f"wrote {out} — {len(entries)} certificates: {by_class}")


if __name__ == "__main__":
    main()
