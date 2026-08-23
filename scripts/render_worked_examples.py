#!/usr/bin/env python3
"""Re-render the certificate texts that ship outside a milestone directory.

Three published renders live in worked-example directories rather than under a class's
`milestone/certificates/`: the metformin PK/PD certificate the README and `docs/mcp-server.md`
send readers to, the E. coli core constraint-based one, and the logical toggle switch. Nothing
regenerated them, so they drifted: the metformin text was still naming an engine pin with no judge
revision, and a protocol line produced by code that no longer exists. `tests/test_pins.py` now
gates every committed render against the current revision, and this is the script that satisfies
it. Run from the repo root, after the milestone scripts:

    python scripts/render_worked_examples.py
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import (
    Certificate,
    PaperIdentity,
    RunMetadata,
    certificate_from_content,
    certify_logical,
    render_human,
)
from reprolith.constraint_based import certify_constraint_based
from reprolith.fba import solver_pin as fba_pin
from reprolith.logical import LogicalClaim
from reprolith.logical import solver_pin as logical_pin
from reprolith.persistence import dossier_from_dict

ROOT = Path(__file__).parent.parent
#: One fixed stamp for every render this script writes; run metadata is outside the content hash
#: and `render_human` prints none of it, so this keeps each render reproducible byte for byte.
_RUN = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1")
DATASETS = ROOT / "datasets"

# Each render, and the committed certificate it is the rendering *of*. Re-rendering from the
# machine-readable certificate is what keeps the two accounts of one result from disagreeing —
# which is exactly how the metformin text came to publish a weaker pin than its own JSON.
FROM_JSON = [
    (
        DATASETS / "milestone" / "certificates" / "BIOMD0000001028.json",
        DATASETS / "worked_examples" / "metformin_reproduction_certificate.txt",
    ),
]

_CB = DATASETS / "constraint_based"


def _e_coli_certificate() -> Certificate:
    """Re-certified from the worked example's own dossier, not from the milestone certificate.

    The milestone run certifies the same model from the same dossier but under a PaperIdentity
    carrying no doi, so rendering the worked example from that JSON would silently drop the
    citation the worked example exists to teach.
    """
    dossier = dossier_from_dict(
        json.loads((_CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
    )
    cert = certify_constraint_based(
        dossier,
        sbml=(_CB / "e_coli_core.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(
            title="E. coli core metabolic model (Orth, Fleming & Palsson 2010)",
            doi="10.1128/ecosalplus.10.2.1",
        ),
        engine_pin=fba_pin(),
    )
    return cert


# The toggle switch has no milestone certificate — it is built from its two claims, and
# `tests/test_logical_worked_example.py` regenerates it byte for byte, so the recipe lives in both
# places and must stay identical.
_TOGGLE_RULES = {"A": "!B", "B": "!A"}


def _toggle_certificate() -> Certificate:
    cert = certify_logical(
        paper=PaperIdentity(
            title="Toggle switch — a two-gene mutual-repression circuit", doi="10.0/toggle"
        ),
        engine_pin=logical_pin(),
        claims=[
            LogicalClaim(claim_id="ss_on", quantity="A-ON steady state", rules=_TOGGLE_RULES,
                         reported={"A": 1, "B": 0}, source_location="Fig 1a"),
            LogicalClaim(claim_id="ss_off", quantity="A-OFF steady state", rules=_TOGGLE_RULES,
                         reported={"A": 0, "B": 1}, source_location="Fig 1b"),
        ],
    )
    return cert


def main() -> None:
    for source, target in FROM_JSON:
        content = json.loads(source.read_text(encoding="utf-8"))
        cert = certificate_from_content(content)
        # The committed certificate stores content only — run metadata is deliberately outside the
        # deterministic hash — and render_human prints none of it, so a fixed stamp keeps this
        # render reproducible byte for byte.
        run = RunMetadata(
            created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1"
        )
        target.write_text(render_human(cert, run) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)} from {source.relative_to(ROOT)}")

    # Each of these two is rendered from a certificate this script builds rather than from one a
    # milestone published — the E. coli worked example re-certifies under a PaperIdentity carrying
    # the doi the milestone entry drops, and the toggle switch is built from its two claims. The
    # certificate is written out beside the render so the freshness gate can compare them byte for
    # byte, instead of having no sibling and being skipped, which is how a hand-edited verdict in a
    # committed render went unnoticed.
    for certificate, directory in (
        (_e_coli_certificate(), _CB / "worked_example"),
        (_toggle_certificate(), DATASETS / "logical" / "worked_example"),
    ):
        (directory / "certificate.txt").write_text(
            render_human(certificate, _RUN) + "\n", encoding="utf-8"
        )
        (directory / "certificate.json").write_text(
            json.dumps(certificate.content(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {(directory / 'certificate.txt').relative_to(ROOT)} and its certificate.json")


if __name__ == "__main__":
    main()
