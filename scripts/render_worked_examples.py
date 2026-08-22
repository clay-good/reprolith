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


def _e_coli_certificate() -> str:
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
    run = RunMetadata(
        created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1"
    )
    return render_human(cert, run) + "\n"


# The toggle switch has no milestone certificate — it is built from its two claims, and
# `tests/test_logical_worked_example.py` regenerates it byte for byte, so the recipe lives in both
# places and must stay identical.
_TOGGLE_RULES = {"A": "!B", "B": "!A"}


def _toggle_certificate() -> str:
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
    run = RunMetadata(
        created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1"
    )
    return render_human(cert, run) + "\n"


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

    target = _CB / "worked_example" / "certificate.txt"
    target.write_text(_e_coli_certificate(), encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")

    target = DATASETS / "logical" / "worked_example" / "certificate.txt"
    target.write_text(_toggle_certificate(), encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
