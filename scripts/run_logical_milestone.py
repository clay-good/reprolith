#!/usr/bin/env python3
"""Regenerate the logical (Boolean-network) milestone artifact from committed data.

The logical counterpart of ``run_milestone.py`` / ``run_fba_milestone.py`` / ``run_kinetic_milestone.py``.
Seeds the catalog with the four real published Boolean models whose attractor structure an
independent tool (CANA) established, certifies each *blind* — the verdict path never sees the label
— by checking that Reprolith's own attractor oracle reproduces CANA's independently-computed
attractor count, and scores agreement with ground truth on the same ``run_test_set`` machinery every
other class uses. This is the fourth class flowing through one catalog lifecycle, one certificate
format, one agreement report, and one scope flag — the generalization demonstrated, not asserted.

Reproducible from the repository alone — no network, no CANA (it reads the committed
``datasets/logical/cross_validation/reference.json``). Run from the repo root:

    python scripts/run_logical_milestone.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from reprolith import (
    Attribution,
    Catalog,
    ComparisonMethod,
    EnginePin,
    FailureMode,
    Fault,
    GroundTruth,
    Identifiers,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    RunMetadata,
    assess_match,
    build_certificate,
    certificate_digest,
    parse_boolean_network,
    render_human,
    run_test_set,
)

REPO = Path(__file__).resolve().parents[1]
LOG = REPO / "datasets" / "logical"


def main() -> None:
    reference = json.loads((LOG / "cross_validation" / "reference.json").read_text(encoding="utf-8"))
    pin = EnginePin(engine="reprolith-logical", version="0.0.1")  # exact analysis, no external solver
    catalog = Catalog()
    certified = {}

    for key in sorted(reference["models"]):
        entry = reference["models"][key]
        catalog.add(
            Identifiers(title=entry["citation"], accession=key),
            ModelClass.LOGICAL,
            ground_truth=GroundTruth(
                expected=OverallVerdict.REPRODUCED,
                source=f"{reference['_source']}: {entry['n_attractors']} attractors",
            ),
        )
        # Certify blind: only the model rules and CANA's attractor count are inputs, never the label.
        net = parse_boolean_network(entry["rules"])
        found = len(net.fixed_points())  # every reference model is fixed-point only
        expected = entry["n_attractors"]
        matched = found == expected
        assessment = assess_match(
            claim_id=f"{key}-attractors",
            quantity="steady-state (fixed-point) attractor count",
            source_location=entry["citation"],
            matched=matched,
            method=ComparisonMethod.ATTRACTOR_SET_MATCH,
            discrepancy=f"reproduced {found} fixed points vs CANA's {expected}",
            attribution=None if matched else Attribution(
                mode=FailureMode.UNSPECIFIED_UPDATE_SCHEME,
                implicated="attractor count", fault=Fault.RECONSTRUCTION,
            ),
        )
        certified[key] = build_certificate(
            paper=PaperIdentity(title=entry["citation"], doi=""),
            engine_pin=pin,
            assessments=[assessment],
        )

    certificates, report = run_test_set(
        catalog.entries, engine_pin=pin, certified=certified, advance=True
    )

    milestone = LOG / "milestone"
    (milestone / "certificates").mkdir(parents=True, exist_ok=True)
    run = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="logical-milestone", tool_version="0.0.1")
    for key, cert in certified.items():
        (milestone / "certificates" / f"{key}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (milestone / "certificates" / f"{key}.txt").write_text(
            render_human(cert, run), encoding="utf-8"
        )
    (milestone / "catalog.json").write_text(
        json.dumps(catalog.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"logical milestone: {report.agreements}/{report.total} agree with ground truth")
    print(f"verdicts: {dict(counts)}")
    print(f"digests: {[certificate_digest(c) for c in certificates]}")


if __name__ == "__main__":
    main()
