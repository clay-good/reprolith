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
