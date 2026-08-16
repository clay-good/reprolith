"""SBML-qual ingestion into a BooleanNetwork (logical-class front-end; roadmap #9).

The logical counterpart of the FBA `ingest_fbc_sbml`: parse a standard SBML-qual logical model
into the network the logical oracle judges. Needs the engine extra (python-libsbml, which bundles
the qual package); the tests skip without it. The fixtures are committed, so these exercise only
the read path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")

from reprolith import ingest_qual_sbml, judge_steady_state  # noqa: E402

_FIX = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def test_ingest_toggle_recovers_its_fixed_points() -> None:
    # A=!B, B=!A: the two fixed points and the synchronous 2-cycle must come back from the qual file.
    net = ingest_qual_sbml(_read("toggle_qual.xml"))
    assert net.nodes == ("A", "B")
    assert {tuple(sorted(fp.items())) for fp in net.fixed_points()} == {
        (("A", 0), ("B", 1)),
        (("A", 1), ("B", 0)),
    }
    assert sorted(len(a) for a in net.attractors()) == [1, 1, 2]  # the 2-cycle survives


def test_ingested_toggle_feeds_the_oracle_end_to_end() -> None:
    net = ingest_qual_sbml(_read("toggle_qual.xml"))
    ok = judge_steady_state(
        claim_id="ss", quantity="ON state", source_location="Fig 1",
        reported={"A": 1, "B": 0}, network=net,
    )
    assert ok.verdict.value == "reproduced"


def test_ingest_and_network_with_holding_inputs() -> None:
    # C = A and B, with A and B as input nodes that have no transition and hold their value.
    net = ingest_qual_sbml(_read("and_inputs_qual.xml"))
    assert net.nodes == ("A", "B", "C")
    # C is 1 only when both inputs are 1; the inputs are free, so each input combination is a
    # fixed point once C settles — four in total.
    fixed = {tuple(sorted(fp.items())) for fp in net.fixed_points()}
    assert fixed == {
        (("A", 0), ("B", 0), ("C", 0)),
        (("A", 0), ("B", 1), ("C", 0)),
        (("A", 1), ("B", 0), ("C", 0)),
        (("A", 1), ("B", 1), ("C", 1)),
    }
    # An input holds its value: stepping from a state leaves A and B unchanged.
    assert net.step({"A": 1, "B": 0, "C": 0}) == {"A": 1, "B": 0, "C": 0}


def test_multi_level_species_is_rejected() -> None:
    import libsbml as libsbml_mod

    ns = libsbml_mod.QualPkgNamespaces(3, 1)
    doc = libsbml_mod.SBMLDocument(ns)
    doc.setPackageRequired("qual", True)
    model = doc.createModel()
    comp = model.createCompartment()
    comp.setId("c")
    comp.setConstant(True)
    qual = model.getPlugin("qual")
    species = qual.createQualitativeSpecies()
    species.setId("M")
    species.setCompartment("c")
    species.setConstant(False)
    species.setMaxLevel(2)  # ternary — the Boolean oracle must refuse it
    species.setInitialLevel(0)
    with pytest.raises(ValueError, match="two-level"):
        ingest_qual_sbml(libsbml_mod.writeSBMLToString(doc))


def _qual_document(*, initial_level: int = 0, formula: str = "Signal >= 1",
                   default_term: bool = True, output_effect: str = "assignment",
                   input_threshold: int | None = None) -> str:
    """A two-species qual model — `Target := formula` over a constant input `Signal`."""
    import libsbml

    doc = libsbml.SBMLDocument(libsbml.SBMLNamespaces(3, 1, "qual", 1))
    model = doc.createModel()
    qual = model.getPlugin("qual")
    compartment = model.createCompartment()
    compartment.setId("c")
    compartment.setConstant(True)
    for species_id, level, constant in (("Signal", initial_level, True), ("Target", 0, False)):
        species = qual.createQualitativeSpecies()
        species.setId(species_id)
        species.setCompartment("c")
        species.setConstant(constant)
        species.setInitialLevel(level)  # maxLevel deliberately left unset, as real files often do
    transition = qual.createTransition()
    transition.setId("t1")
    model_input = transition.createInput()
    model_input.setId("i1")
    model_input.setQualitativeSpecies("Signal")
    model_input.setTransitionEffect(libsbml.INPUT_TRANSITION_EFFECT_NONE)
    if input_threshold is not None:
        model_input.setThresholdLevel(input_threshold)
    output = transition.createOutput()
    output.setQualitativeSpecies("Target")
    output.setTransitionEffect(
        libsbml.OUTPUT_TRANSITION_EFFECT_ASSIGNMENT_LEVEL if output_effect == "assignment"
        else libsbml.OUTPUT_TRANSITION_EFFECT_PRODUCTION
    )
    if default_term:
        transition.createDefaultTerm().setResultLevel(0)
    term = transition.createFunctionTerm()
    term.setResultLevel(1)
    term.setMath(libsbml.parseL3Formula(formula))
    return libsbml.writeSBMLToString(doc)


def test_a_multi_valued_model_without_max_level_is_refused_not_flattened() -> None:
    # maxLevel is optional, so its absence is no evidence the model is Boolean. A three-level input
    # driving `Target := (Signal >= 2)` used to ingest as Boolean: the threshold became permanently
    # false, the model's real dynamics vanished, and a state that is NOT a steady state of the
    # actual model was certified as reproduced.
    with pytest.raises(ValueError, match="multi-valued"):
        ingest_qual_sbml(_qual_document(initial_level=2))
    # The level also shows up in the math, which is caught even when no species declares it.
    with pytest.raises(ValueError, match="two-level"):
        ingest_qual_sbml(_qual_document(formula="Signal >= 2"))
    # The genuinely Boolean model is untouched.
    assert ingest_qual_sbml(_qual_document()).nodes == ("Signal", "Target")


def test_unsupported_qual_transition_constructs_are_refused() -> None:
    # Each of these means something the Boolean oracle does not do; running them as ordinary
    # assignment logic silently certifies a different model.
    with pytest.raises(ValueError, match="produces rather than assigns"):
        ingest_qual_sbml(_qual_document(output_effect="production"))
    with pytest.raises(ValueError, match="no default term"):
        ingest_qual_sbml(_qual_document(default_term=False))
    with pytest.raises(ValueError, match="threshold level"):
        ingest_qual_sbml(_qual_document(input_threshold=3))


def test_the_ingested_network_carries_its_rules_so_a_large_model_stays_solvable() -> None:
    # Ingestion used to return closures only, and the scalable SAT path needs the symbolic rules —
    # so every SBML-qual model above the enumeration ceiling refused, which is exactly the size of
    # the real signalling models the scalable path exists for. The rules now come back with it.
    net = ingest_qual_sbml(_read("toggle_qual.xml"))
    assert net.expressions is not None
    assert set(net.expressions) == {"A", "B"}


def test_emitted_rules_reproduce_the_qual_semantics_exactly() -> None:
    # The rules are written from the function terms, so they have to mean what the terms mean:
    # ordered terms (a later term only decides when every earlier one missed), the default level,
    # level comparisons in both directions, and comparisons between two species.
    import itertools

    from reprolith import compile_boolean_rule
    from reprolith.sbml import _qual_condition_expression, _qual_rule_expression

    # Ordered terms: B's rule is "first term wins", so term 2 only applies when term 1 missed.
    rule = _qual_rule_expression([("A", 0), ("C", 1)], default_level=1)
    predicted = compile_boolean_rule(rule, {"A", "C"})
    for a, c in itertools.product((0, 1), repeat=2):
        expected = 0 if a else (1 if c else 1)  # term1 -> 0, else term2 -> 1, else default 1
        assert predicted({"A": a, "C": c}) == expected, (a, c, rule)

    # Level comparisons, including species-to-species, over both operand orders.
    import libsbml

    for formula, expected in (
        ("A >= 1", lambda a, b: a),
        ("A == 0", lambda a, b: 1 - a),
        ("1 <= A", lambda a, b: a),
        ("A > B", lambda a, b: int(a > b)),
        ("A == B", lambda a, b: int(a == b)),
        ("A != B", lambda a, b: int(a != b)),
        ("A >= 0", lambda a, b: 1),
    ):
        expression = _qual_condition_expression(
            libsbml.parseL3Formula(formula), libsbml, {"A", "B"}
        )
        compiled = compile_boolean_rule(expression, {"A", "B"})
        for a, b in itertools.product((0, 1), repeat=2):
            assert compiled({"A": a, "B": b}) == expected(a, b), (formula, expression, a, b)
