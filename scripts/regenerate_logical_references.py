"""Regenerate the logical-class cross-validation references from the CANA library.

This is a dev-only tool (the ``refgen`` extra), not a runtime dependency of Reprolith. It uses
CANA (Correia et al. 2018) — an independent Boolean-network library — as the non-circular oracle
for the logical class, exactly as ``regenerate_fba_references.py`` uses COBRApy and
``regenerate_kinetic_references.py`` uses libRoadRunner. For each real, published Boolean model
CANA bundles, it:

1. exports every node's CANA truth table to a Reprolith Boolean rule expression, and
2. *proves the export is faithful* by checking the compiled rule against CANA's own per-node step
   for every input combination — so the committed rules are provably CANA's model, not a guess, and
3. records CANA's independently-computed attractor signature (the number of attractors and their
   periods), which is invariant to CANA's constant-node reduction and to state encoding.

The committed ``reference.json`` then lets ``tests/test_logical_cross_validation.py`` check that
Reprolith's own attractor computation reproduces CANA's signature on these models using only
runtime code — no CANA needed at test time.

Run: ``python scripts/regenerate_logical_references.py`` (needs ``pip install -e ".[refgen]"``).
"""

from __future__ import annotations

import json
import re
import sys
from itertools import product
from pathlib import Path

# The published models to cross-validate against, with the citation CANA records for each.
_PUBLISHED = {
    "thaliana": ("THALIANA", "Arabidopsis thaliana flower morphogenesis (Chaos et al. 2006)"),
    "drosophila": ("DROSOPHILA", "Drosophila melanogaster segment polarity, single cell (Albert & Othmer 2003)"),
    "budding_yeast": ("BUDDING_YEAST", "Budding yeast cell-cycle network (Li et al. 2004)"),
    "marques_pita": ("MARQUESPITA", "Two-symbol schemata example network (Marques-Pita & Rocha 2013)"),
}

# Synthetic networks with cyclic attractors, so the limit-cycle path (not just fixed points) is
# cross-validated against CANA. Given as CANA rule strings; CANA is still the independent oracle.
_SYNTHETIC = {
    "repressilator": (
        "A*= not C\nB*= not A\nC*= not B\n",
        "Three-gene repressilator ring — a synchronous limit cycle, no fixed point",
    ),
    "toggle_plus_switch": (
        "A*= not B\nB*= not A\nC*= C\n",
        "A mutual-repression toggle (2-cycle) crossed with a bistable self-activating switch",
    ),
}

_OUT = Path(__file__).resolve().parents[1] / "datasets" / "logical" / "cross_validation"


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"\W", "_", name)
    return cleaned if cleaned[:1].isalpha() or cleaned[:1] == "_" else "n_" + cleaned


def _export_rules(bn: object) -> dict[str, str]:
    """Export each CANA node's truth table to a Reprolith Boolean rule (DNF over its inputs)."""
    from cana.utils import statenum_to_binstate

    labels = [_sanitize(node.name) for node in bn.nodes]  # type: ignore[attr-defined]
    if len(set(labels)) != len(labels):
        raise ValueError("node names collide after sanitisation")
    rules: dict[str, str] = {}
    for node, label in zip(bn.nodes, labels):  # type: ignore[attr-defined]
        inputs = [labels[i] for i in node.inputs]
        if node.k == 0 or not inputs:
            rules[label] = "1" if str(node.outputs[0]) == "1" else "0"
            continue
        terms = []
        for row, output in enumerate(node.outputs):
            if str(output) != "1":
                continue
            bits = statenum_to_binstate(row, base=node.k)
            terms.append("(" + " & ".join(
                inp if bits[p] == "1" else f"!{inp}" for p, inp in enumerate(inputs)
            ) + ")")
        rules[label] = " | ".join(terms) if terms else "0"
    return rules


def _assert_faithful(bn: object, rules: dict[str, str]) -> None:
    """Prove the exported rules reproduce CANA's per-node dynamics over every input combination."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
    from reprolith import compile_boolean_rule

    labels = [_sanitize(node.name) for node in bn.nodes]  # type: ignore[attr-defined]
    names = set(labels)
    for node, label in zip(bn.nodes, labels):  # type: ignore[attr-defined]
        inputs = [labels[i] for i in node.inputs]
        if not inputs:
            continue
        rule = compile_boolean_rule(rules[label], names)
        for combo in product((0, 1), repeat=len(inputs)):
            mine = rule(dict(zip(inputs, combo)))
            theirs = int(str(node.step("".join(str(b) for b in combo))))
            if mine != theirs:
                raise AssertionError(f"export unfaithful at node {node.name!r}")


def main() -> None:
    try:
        import cana  # noqa: F401
        import cana.datasets.bio as bio
    except ImportError as exc:
        raise SystemExit("this script needs the refgen extra: pip install -e \".[refgen]\"") from exc

    from cana.boolean_network import BooleanNetwork as CanaNetwork

    networks = {key: (getattr(bio, loader)(), citation) for key, (loader, citation) in _PUBLISHED.items()}
    networks.update(
        {key: (CanaNetwork.from_string_boolean(rules), citation) for key, (rules, citation) in _SYNTHETIC.items()}
    )

    reference = {"_source": f"CANA {cana.__version__} (Correia et al. 2018)", "models": {}}
    for key in sorted(networks):
        bn, citation = networks[key]
        rules = _export_rules(bn)
        _assert_faithful(bn, rules)  # committed rules are provably CANA's model
        periods = sorted(len(attractor) for attractor in bn.attractors())
        reference["models"][key] = {
            "citation": citation,
            "n_nodes": bn.Nnodes,
            "rules": rules,
            "n_attractors": len(periods),
            "attractor_periods": periods,
        }
        print(f"{key}: {bn.Nnodes} nodes, {len(periods)} attractors, periods {sorted(set(periods))}")

    _OUT.mkdir(parents=True, exist_ok=True)
    (_OUT / "reference.json").write_text(
        json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {_OUT / 'reference.json'}")


if __name__ == "__main__":
    main()
