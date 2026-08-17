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
from pathlib import Path

from reprolith import certificate_digest, certificate_from_content, render_registry
from reprolith.mcp_server import milestone_agreement_reports, milestone_certificate_dirs
from reprolith.query import self_validation_summary

# Each class's milestone certificate directory and the model-class label it certifies — the same
# source of truth the read surfaces aggregate into the query ledger, so the registry and the
# queryable surface can never list a different set of certificates. Read and write both hang off
# this one root (the imported package's datasets dir), so the registry can't be built from one
# checkout's certificates and written into another's.
_SOURCES = milestone_certificate_dirs()
_DATASETS = _SOURCES["ode-pkpd"].parents[1]  # .../datasets
_HERE = Path(__file__).resolve().parents[1] / "datasets"


def collect() -> list[tuple[str, object]]:
    """Every committed certificate, once, keyed by content digest like the queryable ledger.

    The registry counted files while the ledger keys by digest, so one certificate copied into a
    second class directory made the published "N certificates" headline disagree with the surface
    it claims parity with — and filed the copy under the wrong class. Collect by digest instead,
    and refuse a duplicate that claims two different classes rather than picking one silently.
    """
    entries: list[tuple[str, object]] = []
    seen: dict[str, str] = {}  # digest -> the class it was first collected under
    for model_class, directory in _SOURCES.items():
        # A missing directory globs to nothing, so a class whose milestone had not been run simply
        # vanished from the page — exit 0, no warning, and a smaller published track record
        # asserted as the truth. A class this builder knows about must be there.
        if not directory.is_dir():
            raise FileNotFoundError(
                f"no milestone certificates for the {model_class!r} class at {directory}; "
                "run that class's milestone script rather than publishing a page without it"
            )
        for path in sorted(directory.glob("*.json")):
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
                certificate = certificate_from_content(content)
            except (ValueError, KeyError) as exc:
                # Otherwise a stray or truncated file fails anonymously, with nothing naming it.
                raise ValueError(f"{path} is not a readable certificate: {exc}") from exc
            digest = certificate_digest(certificate)
            if digest in seen:
                if seen[digest] != model_class:
                    raise ValueError(
                        f"{path} holds a certificate already published under {seen[digest]!r}; one "
                        f"certificate cannot certify both that class and {model_class!r}"
                    )
                continue  # the same certificate committed twice under one class — publish it once
            seen[digest] = model_class
            entries.append((model_class, certificate))
    return entries


def main() -> None:
    # The certificates come from the imported package's datasets directory. In a worktree with the
    # package resolved from another checkout, that is not this script's repository — and the page
    # was written there, silently rewriting a different checkout's registry and leaving this one
    # stale. Publish only when the two agree, and say so plainly when they do not.
    if _DATASETS != _HERE:
        raise SystemExit(
            f"reprolith is imported from {_DATASETS}, but this script lives in {_HERE}. "
            f'Run it with PYTHONPATH="{_HERE.parent / "python"}" so the page is built from, '
            "and written to, one checkout."
        )
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
