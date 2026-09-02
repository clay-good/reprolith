"""What a claim's verdict rests on, read out of the model that produces it.

A claim's **footprint** is the set of model elements its value is computed from. It is what two
claims can *share*, and so the only thing that makes a set of them more or less independent
evidence than the sum of its members — which is the input :mod:`reprolith.selection` needs and
which nothing in this repository produced.

The derivation is a **measurement**, and that is the whole point of doing it here rather than
against a claim's free-text description. An SBML model states, in machine-readable form, which
symbols each quantity is computed from: its reactions' rate laws, its assignment and rate rules,
its initial assignments, the compartment a species sits in, and the function definitions those
call. Walking that graph is reading the model. Matching parameter names out of a claim's
``quantity`` string would invent a dependency and then let a selection be defended by it, which
the ``claim-selection`` spec refuses on purpose.

This reads the *model file* rather than the dossier, and the difference is load-bearing on the
corpus as it stands: `ingest_sbml` declines to carry a reaction network it cannot represent
faithfully and records it as a gap, so on the metformin models — whose dynamics are 33 reactions
— a dossier-level walk reaches nothing at all for a species claim. Measured before this was
written: 77 of the corpus's 80 claims resolved to a footprint containing only themselves.

Needs the ``engine`` extra (python-libsbml), like every other reader of a model file.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

#: Everything in a rendered expression that could be a name. Numbers, operators and punctuation
#: are not, so `2 * k_el` yields `k_el` alone. Deliberately not a parser: the caller keeps only the
#: tokens the model itself declares, so a stray token is dropped by that filter rather than by a
#: grammar this would have to maintain — and a token missed here can only ever *shrink* a
#: footprint, which selection reads as "not characterized" rather than as independence.
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _symbols(formula: str) -> frozenset[str]:
    return frozenset(_SYMBOL.findall(formula))


def _dependency_graph(model: object, libsbml: object) -> dict[str, frozenset[str]]:
    """Every model element, and the elements its value is computed from.

    One edge kind per way SBML has of saying "this is computed from that", and no others — an
    edge this does not know about can only leave a footprint smaller than the truth.
    """
    to_formula = libsbml.formulaToL3String  # type: ignore[attr-defined]
    edges: dict[str, set[str]] = {}

    def depends(name: str, on: Iterable[str]) -> None:
        edges.setdefault(name, set()).update(on)

    for index in range(model.getNumSpecies()):  # type: ignore[attr-defined]
        species = model.getSpecies(index)  # type: ignore[attr-defined]
        # A concentration is an amount over a volume, so the compartment is machinery the claim
        # rests on — and it is what two claims read in the same tissue actually share.
        depends(species.getId(), [species.getCompartment()])

    for index in range(model.getNumReactions()):  # type: ignore[attr-defined]
        reaction = model.getReaction(index)  # type: ignore[attr-defined]
        law = reaction.getKineticLaw()
        rate = _symbols(to_formula(law.getMath())) if law is not None and law.isSetMath() else frozenset()
        # The reaction is a node of its own, not just a conduit: two claims moved by one reaction
        # share that reaction whether or not they share any symbol in its rate law.
        depends(reaction.getId(), rate)
        changed = [
            reference.getSpecies()
            for group in (reaction.getListOfReactants(), reaction.getListOfProducts())
            for reference in group
        ]
        for species in changed:
            depends(species, [reaction.getId()])

    for index in range(model.getNumRules()):  # type: ignore[attr-defined]
        rule = model.getRule(index)  # type: ignore[attr-defined]
        if rule.isSetMath():
            # Assignment, rate and algebraic rules alike: each states that its variable is
            # computed from the symbols on its right-hand side.
            depends(rule.getVariable() or "", _symbols(to_formula(rule.getMath())))

    for index in range(model.getNumInitialAssignments()):  # type: ignore[attr-defined]
        assignment = model.getInitialAssignment(index)  # type: ignore[attr-defined]
        if assignment.isSetMath():
            depends(assignment.getSymbol(), _symbols(to_formula(assignment.getMath())))

    for index in range(model.getNumFunctionDefinitions()):  # type: ignore[attr-defined]
        definition = model.getFunctionDefinition(index)  # type: ignore[attr-defined]
        if definition.isSetMath():
            # A shared function is shared machinery, and every one of these models routes its
            # tissue flows through the same handful of them.
            depends(definition.getId(), _symbols(to_formula(definition.getMath())))

    return {name: frozenset(on) for name, on in edges.items()}


def _vocabulary(model: object) -> frozenset[str]:
    """Every name this model declares — the only names allowed into a footprint.

    A rate law's rendered text carries operators, literals and the bound variables of the
    functions it calls. Keeping only declared ids means a footprint element always names
    something the model has, so an element can be looked up rather than taken on trust.
    """
    names: list[str] = []
    for count, get in (
        (model.getNumSpecies(), model.getSpecies),  # type: ignore[attr-defined]
        (model.getNumParameters(), model.getParameter),  # type: ignore[attr-defined]
        (model.getNumCompartments(), model.getCompartment),  # type: ignore[attr-defined]
        (model.getNumReactions(), model.getReaction),  # type: ignore[attr-defined]
        (model.getNumFunctionDefinitions(), model.getFunctionDefinition),  # type: ignore[attr-defined]
    ):
        names.extend(get(index).getId() for index in range(count))
    return frozenset(name for name in names if name)


def derive_footprints(
    sbml: str, targets: Iterable[str], *, depth: int = 2
) -> Mapping[str, frozenset[str]]:
    """Each target's footprint: what the model says its value is computed from, transitively.

    One parse for every target, because a paper's claims are read off one model and re-reading it
    per claim is the difference between a second and a minute on a genome-scale file.

    ``depth`` is how many dependency hops are walked, and **2 is a measured choice, not a
    default**. The transitive closure is the obvious answer and it is useless here: a PBPK model is
    strongly connected — plasma feeds every tissue and every tissue feeds plasma — so the closure
    from any species is the whole model, and on this corpus every one of the 80 claims came back
    with an identical 116-element footprint. Identical footprints overlap completely, so a
    selection over them reports that reproducing any one claim makes every other worthless, which
    is a statement about the walk rather than about the paper. Measured over one paper's ten
    tissues at three doses, mean pairwise Jaccard overlap runs 0.01 at depth 1, **0.20 at depth 2**,
    0.37 at depth 3 and 1.0 at closure. Depth 2 is where a claim reaches its own machinery — its
    tissue's partition coefficient, that tissue's blood flow, the two transport reactions moving
    drug in and out of it, and the shared arterial pool and flow function every tissue routes
    through — which is what a reproduction of that claim actually exercises. Depth 1 stops before
    the shared machinery and reports every claim as independent; depth 3 begins collapsing back
    toward the closure.

    A target the closure cannot get beyond — no rule, no reaction, nothing — maps to the **empty**
    set, never to ``{itself}``. That distinction is the one this function most has to get right: an
    empty footprint is what selection reads as *not characterized*, while a singleton is a
    characterized claim that overlaps nothing, and thirty-three views of one model each carrying
    their own name would be reported as thirty-three independent pieces of evidence. Measured on
    this corpus before the rule existed, that is exactly what a dossier-level walk produced.
    """
    from .sbml import _libsbml

    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(sbml)
    model = document.getModel()
    if model is None:
        raise ValueError("this artifact holds no model, so nothing states what a claim rests on")
    graph = _dependency_graph(model, libsbml)
    vocabulary = _vocabulary(model)

    derived: dict[str, frozenset[str]] = {}
    for target in targets:
        if target in derived:
            continue
        if target not in vocabulary:
            derived[target] = frozenset()
            continue
        reached: set[str] = {target}
        frontier = {target}
        for _ in range(depth):
            frontier = {
                on
                for name in frontier
                for on in graph.get(name, ())
                if on in vocabulary and on not in reached
            }
            reached |= frontier
        derived[target] = frozenset() if reached == {target} else frozenset(reached)
    return derived


def _libsbml_vocabulary_for_test(sbml: str) -> frozenset[str]:
    """Every name a model declares — exposed so a test can hold footprints to it."""
    from .sbml import _libsbml

    return _vocabulary(_libsbml().readSBMLFromString(sbml).getModel())


__all__ = ["derive_footprints"]
