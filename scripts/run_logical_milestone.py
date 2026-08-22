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

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from reprolith import (
    Attribution,
    Catalog,
    ComparisonMethod,
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
    search_protocol,
)
from reprolith.logical import require_pin_matches_path, solver_pin, solver_pin_for
from reprolith.mcp_server import write_json_atomically
from reprolith.persistence import prune_certificate_directory


def _fixed_point_digest(net, fixed) -> str:
    """SHA-256 of the fixed-point set, in the convention the committed reference publishes."""
    encoded = sorted("".join(str(state[n]) for n in net.nodes) for state in fixed)
    return hashlib.sha256("\n".join(encoded).encode("utf-8")).hexdigest()


REPO = Path(__file__).resolve().parents[1]
LOG = REPO / "datasets" / "logical"


def _cited(citation: str, reference_tool: str) -> str:
    """The publication, and the tool that actually produced the number judged against it.

    A `source_location` names where the reference VALUE came from — the claims dataset says so in
    as many words: "A claim's reference value comes from the paper (cited in source_location), not
    from re-running the model." For these entries it did not: the attractor structure was computed
    by an independent tool from the same committed rules, which is what makes the cross-validation
    non-circular. Citing only the publication let the certificate read as a reproduction of the
    paper's own published count, over its own citation, when a reader following that pointer would
    find a different number — the defect already fixed once for the budding-yeast entry, unfixed
    for its neighbours.
    """
    return f"{citation} — reference computed by {reference_tool}, not a count read from the paper"


def main() -> None:
    reference = json.loads((LOG / "cross_validation" / "reference.json").read_text(encoding="utf-8"))
    scalable = json.loads(
        (LOG / "cross_validation" / "scalable_fixed_points.json").read_text(encoding="utf-8")
    )
    # The pin names the update scheme every number here was computed under (the same network has
    # different cyclic attractors under asynchronous updating) and, for the large networks, the SAT
    # solver that actually found their fixed points.
    pin = solver_pin()
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
        plans.append((key, entry["rules"], _cited(entry["citation"], reference["_source"]),
                      "attractors",
                      (entry["n_attractors"], sorted(entry["attractor_periods"])),
                      "attractor signature (count and periods)",
                      "the attractor count and every period",
                      f"{reference['_source']}: {entry['n_attractors']} attractors, "
                      f"periods {sorted(entry['attractor_periods'])}"))
    for key in sorted(scalable["models"]):
        entry = scalable["models"][key]
        # The reference publishes the SHA-256 of the fixed-point set itself, so compare that: a
        # count alone is satisfied by any network with the same number of steady states, and
        # single-rule inversions of these very models keep the count while sharing not one state.
        plans.append((key, entry["rules"], _cited(entry["citation"], scalable["_source"]),
                      "fixed_points",
                      (entry["n_fixed_points"], entry["fixed_points_sha256"]),
                      "steady-state (fixed-point) set",
                      "the fixed-point set (SHA-256 of the sorted states)",
                      f"{scalable['_source']}: {entry['n_fixed_points']} fixed points, "
                      f"set digest {entry['fixed_points_sha256'][:12]}…"))

    for key, rules, citation, kind, expected, quantity, exact_on, source in plans:
        catalog.add(
            Identifiers(title=citation, accession=key),
            ModelClass.LOGICAL,
            ground_truth=GroundTruth(expected=OverallVerdict.REPRODUCED, source=source),
        )
        # Certify blind: only the model rules and the independent count are inputs, never the label.
        net = parse_boolean_network(rules)
        # Compare the whole signature the independent reference supports — how many attractors,
        # and the length of each — not the count alone. Agreeing on a count while disagreeing on
        # every period is not a reproduction, and a certificate that says "set match" while
        # comparing one integer claims more than it checked.
        if kind == "attractors":
            attractors = net.attractors()
            found = (len(attractors), sorted(len(a) for a in attractors))
            method = ComparisonMethod.ATTRACTOR_SIGNATURE_MATCH
            discrepancy = (f"reproduced {found[0]} attractors with periods {found[1]} vs "
                           f"the independent {expected[0]} with periods {expected[1]}")
        else:
            fixed = net.fixed_points()
            found = (len(fixed), _fixed_point_digest(net, fixed))
            # A set digest is a set match, not a signature match — say so, and pin the solver that
            # produced it: these networks are past the enumeration ceiling and are solved by z3.
            method = ComparisonMethod.ATTRACTOR_SET_MATCH
            discrepancy = (f"reproduced {found[0]} fixed points, set digest {found[1][:12]}… vs "
                           f"the independent {expected[0]}, {expected[1][:12]}…")
        matched = found == expected
        assessment = assess_match(
            claim_id=f"{key}-{kind}",
            quantity=quantity,
            source_location=citation,
            matched=matched,
            method=method,
            exact_on=exact_on,
            discrepancy=discrepancy,
            attribution=None if matched else Attribution(
                mode=FailureMode.UNSPECIFIED_UPDATE_SCHEME,
                implicated=quantity, fault=Fault.RECONSTRUCTION,
            ),
        )
        # The same rule the class front-end uses, from the same helper, so the milestone and
        # `certify_logical` cannot drift about what a logical verdict rests on.
        assessment = replace(assessment, protocol=search_protocol(len(net.nodes)))
        # Which path ran is a fact about the network's size, not a choice made per entry here.
        entry_pin = solver_pin_for(nodes=len(net.nodes))
        # This script builds certificates directly rather than through `certify_logical`, so it
        # runs that front-end's pin check itself: a pin naming exhaustive enumeration over a state
        # space z3 searched is the one claim here that would read stronger than what ran.
        require_pin_matches_path(entry_pin, node_counts=[len(net.nodes)])
        certified[key] = build_certificate(
            paper=PaperIdentity(title=citation, doi=""),
            engine_pin=entry_pin,
            assessments=[assessment],
        )

    certificates, report = run_test_set(
        catalog.entries, engine_pin=pin, certified=certified, advance=True
    )

    milestone = LOG / "milestone"
    (milestone / "certificates").mkdir(parents=True, exist_ok=True)
    prune_certificate_directory(milestone / "certificates", certified)
    run = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="logical-milestone", tool_version="0.0.1")
    for key, cert in certified.items():
        (milestone / "certificates" / f"{key}.json").write_text(
            json.dumps(cert.content(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (milestone / "certificates" / f"{key}.txt").write_text(
            render_human(cert, run), encoding="utf-8"
        )
    # Atomic: this file is what both surfaces read at start-up and what a live MCP server
    # re-reads under its lock, and a plain write_text truncates it to zero before writing
    # ~52 KB. A crash in that window leaves a blank catalog behind.
    write_json_atomically(milestone / "catalog.json", catalog.to_dict())
    (milestone / "agreement_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    counts = Counter(cert.overall.value for cert in certificates)
    print(f"logical milestone: {report.agreements}/{report.total} agree with ground truth")
    print(f"verdicts: {dict(counts)}")
    print(f"digests: {[certificate_digest(c) for c in certificates]}")


if __name__ == "__main__":
    main()
