#!/usr/bin/env python3
"""Regenerate the logical (Boolean-network) milestone artifact from committed data.

The logical counterpart of ``run_milestone.py`` / ``run_fba_milestone.py`` / ``run_kinetic_milestone.py``.
Seeds the catalog with real published Boolean models (plus two synthetic limit-cycle networks) whose
attractor structure an independent tool (CANA) established, certifies each *blind* — the verdict path
never sees the label — by checking that Reprolith's own oracle reproduces the independently-computed
count, and scores agreement with ground truth on the same ``run_test_set`` machinery every other
class uses. Small networks are certified on their full attractor count; the large T-LGL leukemia
network (60 nodes) is certified on its steady-state count via the **scalable** SAT fixed-point path,
where 2⁶⁰ enumeration is impossible — so the milestone exercises that path end to end.

Reproducible from the repository alone — no network, no CANA (it reads the committed
``datasets/logical/cross_validation/``). The leukemia entry needs the ``sat`` extra (z3). Run from
the repo root:

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
    __version__,
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
    scalable = json.loads(
        (LOG / "cross_validation" / "scalable_fixed_points.json").read_text(encoding="utf-8")
    )
    pin = EnginePin(engine="reprolith-logical", version=__version__)  # exact analysis, no external solver
    catalog = Catalog()
    certified = {}

    # (accession, citation, reproduce->count, expected count, quantity, ground-truth note) per model.
    # Small models are certified on their full attractor count (fixed points *and* cyclic attractors,
    # so the synchronous limit cycles of the synthetic networks count correctly, not just steady
    # states); the large models on their steady-state count via the scalable SAT path, since their
    # 2ⁿ state space puts cyclic-attractor enumeration out of reach.
    plans = []
    for key in sorted(reference["models"]):
        entry = reference["models"][key]
        plans.append((key, entry["rules"], entry["citation"], "attractors",
                      entry["n_attractors"], "attractor count",
                      f"{reference['_source']}: {entry['n_attractors']} attractors"))
    for key in sorted(scalable["models"]):
        entry = scalable["models"][key]
        plans.append((key, entry["rules"], entry["citation"], "fixed_points",
                      entry["n_fixed_points"], "steady-state (fixed-point) count",
                      f"{scalable['_source']}: {entry['n_fixed_points']} fixed points"))

    for key, rules, citation, kind, expected, quantity, source in plans:
        catalog.add(
            Identifiers(title=citation, accession=key),
            ModelClass.LOGICAL,
            ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source=source),
        )
        # Certify blind: only the model rules and the independent count are inputs, never the label.
        net = parse_boolean_network(rules)
        found = len(net.attractors()) if kind == "attractors" else len(net.fixed_points())
        matched = found == expected
        assessment = assess_match(
            claim_id=f"{key}-{kind}",
            quantity=quantity,
            source_location=citation,
            matched=matched,
            method=ComparisonMethod.ATTRACTOR_SET_MATCH,
            discrepancy=f"reproduced {found} vs the independent {expected}",
            attribution=None if matched else Attribution(
                mode=FailureMode.UNSPECIFIED_UPDATE_SCHEME,
                implicated=quantity, fault=Fault.RECONSTRUCTION,
            ),
        )
        certified[key] = build_certificate(
            paper=PaperIdentity(title=citation, doi=""),
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
