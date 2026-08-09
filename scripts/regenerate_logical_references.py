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

import hashlib
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

# Large published models — too big for 2ⁿ attractor enumeration, so only their *fixed points* are
# cross-validated (that is what the scalable SAT path targets). Ground truth is computed here by
# sympy's SAT solver, an implementation independent of Reprolith's z3-based one.
_LARGE = {
    "leukemia": ("LEUKEMIA", "T-LGL leukemia signalling network (Zhang et al. 2008)"),
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


def _sympy_node_expr(node: object, symbols: list) -> object:
    """A sympy Boolean expression for a CANA node's truth table — independent of Reprolith's z3."""
    import sympy
    from cana.utils import statenum_to_binstate

    inputs = [symbols[i] for i in node.inputs]  # type: ignore[attr-defined]
    if node.k == 0 or not inputs:  # type: ignore[attr-defined]
        return sympy.true if str(node.outputs[0]) == "1" else sympy.false  # type: ignore[attr-defined]
    terms = []
    for row, output in enumerate(node.outputs):  # type: ignore[attr-defined]
        if str(output) != "1":
            continue
        bits = statenum_to_binstate(row, base=node.k)  # type: ignore[attr-defined]
        terms.append(sympy.And(*[
            inp if bits[p] == "1" else sympy.Not(inp) for p, inp in enumerate(inputs)
        ]))
    return sympy.Or(*terms) if terms else sympy.false


def _sympy_fixed_points(bn: object) -> list[str]:
    """Every fixed point of a CANA network as sorted binary strings, via sympy's SAT (AllSAT).

    A fixed point satisfies ``xᵢ ⟺ fᵢ(x)`` for every node; sympy enumerates all such assignments.
    Free (unconstrained) variables in a model are expanded so the returned set is complete, and
    results are de-duplicated. Independent of Reprolith's z3 solver, so agreement is a real cross-
    tool check, not a tool agreeing with itself. Each state's bits are emitted in **sorted node-name
    order** — the same canonical order Reprolith's ``BooleanNetwork.nodes`` uses — so the SHA-256 of
    the set is comparable across the two implementations.
    """
    import sympy
    from sympy.logic.inference import satisfiable

    labels = [_sanitize(node.name) for node in bn.nodes]  # type: ignore[attr-defined]
    symbols = [sympy.Symbol(labels[i]) for i in range(bn.Nnodes)]  # type: ignore[attr-defined]
    formula = sympy.And(*[
        sympy.Equivalent(symbols[i], _sympy_node_expr(node, symbols))
        for i, node in enumerate(bn.nodes)  # type: ignore[attr-defined]
    ])
    order = sorted(range(len(labels)), key=lambda i: labels[i])  # positional -> sorted-label order
    states: set[str] = set()
    for model in satisfiable(formula, all_models=True):
        if model is False:
            break
        free = [i for i, s in enumerate(symbols) if s not in model]
        base = [1 if model.get(s, False) else 0 for s in symbols]
        for combo in product((0, 1), repeat=len(free)):
            state = list(base)
            for idx, bit in zip(free, combo):
                state[idx] = bit
            states.add("".join(str(state[i]) for i in order))
    return sorted(states)


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

    # Large models: cross-validate the *scalable* fixed-point path only (attractor enumeration is
    # intractable at 60+ nodes). Ground truth from sympy's SAT, independent of Reprolith's z3.
    import cana as _cana

    large = {"_source": f"sympy SAT (independent of Reprolith's z3); rules from CANA {_cana.__version__}",
             "models": {}}
    for key in sorted(_LARGE):
        loader, citation = _LARGE[key]
        bn = getattr(bio, loader)()
        rules = _export_rules(bn)
        _assert_faithful(bn, rules)
        states = _sympy_fixed_points(bn)
        digest = hashlib.sha256("\n".join(states).encode("utf-8")).hexdigest()
        large["models"][key] = {
            "citation": citation,
            "n_nodes": bn.Nnodes,
            "rules": rules,
            "n_fixed_points": len(states),
            "fixed_points_sha256": digest,
        }
        print(f"{key}: {bn.Nnodes} nodes, {len(states)} fixed points (sympy), sha256 {digest[:12]}…")
    (_OUT / "scalable_fixed_points.json").write_text(
        json.dumps(large, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {_OUT / 'scalable_fixed_points.json'}")


if __name__ == "__main__":
    main()
