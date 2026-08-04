"""The constraint-based dossier shape and its end-to-end certification (spec: constraint-based-class).

Two layers. The dossier-shape and validator tests are dependency-free: they exercise the
constraint-based reading of the shared dossier (adopt the model, record the medium as first-class
elements, mark an unstated medium load-bearing) and run in the core CI job. The certification
tests drive the real ingest → solve → certificate pathway on the standard E. coli core model and
need the ``engine`` (python-libsbml with fbc) and ``fba`` (scipy) extras; they skip without them.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from reprolith import (
    Dossier,
    DossierClaim,
    Gap,
    GapKind,
    ModelArtifact,
    Parameter,
    ReferenceKind,
    constraint_based_dossier,
    validate_constraint_based,
)
from reprolith.constraint_based import FLUX_UNIT

_MODEL_PATH = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
_BIOMASS = "R_BIOMASS_Ecoli_core_w_GAM"
# The independently-established aerobic optimum on glucose minimal medium (encoded only here).
_KNOWN_GROWTH_RATE = 0.873922


def _adopted_model() -> ModelArtifact:
    return ModelArtifact(filename="e_coli_core.xml", detected_format="sbml-fbc", validates=True)


def _glucose_aerobic_medium() -> list[Parameter]:
    return [
        Parameter(name="R_EX_glc__D_e", value=10.0, unit=FLUX_UNIT,
                  source_location="e_coli_core default medium (BiGG); glucose-limited"),
        Parameter(name="R_EX_o2_e", value=1000.0, unit=FLUX_UNIT,
                  source_location="e_coli_core default medium (BiGG); aerobic"),
    ]


def _growth_claim() -> DossierClaim:
    return DossierClaim(
        id="growth-glucose-aerobic",
        quantity=f"maximal aerobic growth rate on glucose minimal medium ({_BIOMASS}, maximize)",
        conditions="glucose uptake <= 10 mmol/gDW/h; oxygen unlimited (aerobic)",
        source_location="Orth, Fleming & Palsson (2010); BiGG e_coli_core",
        reference_kind=ReferenceKind.NUMERIC,
        reference_data=(_KNOWN_GROWTH_RATE,),
    )


# --- Dossier shape (dependency-free) --------------------------------------------------------


def test_records_structural_elements_by_reference_and_medium_first_class() -> None:
    # The structural elements live in the adopted model; the medium is recorded first-class, and
    # every recorded element cites a source (the dataclasses make an unsourced element impossible).
    dossier = constraint_based_dossier(
        "bigg-e_coli_core", model=_adopted_model(),
        objective_claims=[_growth_claim()], medium=_glucose_aerobic_medium(),
    )
    assert validate_constraint_based(dossier) == []
    (artifact,) = dossier.artifacts
    assert artifact.detected_format == "sbml-fbc" and artifact.validates
    assert {p.name for p in dossier.parameters} == {"R_EX_glc__D_e", "R_EX_o2_e"}
    assert all(p.source_location for p in dossier.parameters)
    (claim,) = dossier.targetable_claims()
    assert claim.source_location and claim.reference_data == (_KNOWN_GROWTH_RATE,)


def test_unstated_medium_is_recorded_as_a_load_bearing_gap() -> None:
    # A paper that never states its carbon-source limit: recorded as a medium gap, never guessed.
    dossier = constraint_based_dossier(
        "unstated-medium", model=_adopted_model(), objective_claims=[_growth_claim()],
        medium_gaps=[Gap(element="R_EX_glc__D_e", kind=GapKind.MEDIUM,
                         detail="the paper does not state the glucose uptake limit",
                         load_bearing=True)],
    )
    (gap,) = dossier.load_bearing_gaps()
    assert gap.kind is GapKind.MEDIUM and gap.load_bearing


def test_a_medium_gap_must_be_load_bearing() -> None:
    # An unstated medium silently changes the objective, so a non-load-bearing medium gap is
    # a structural error the validator refuses (mirroring how a unit-less Parameter is impossible).
    ill_formed = Dossier(
        entry="e", artifacts=(_adopted_model(),), claims=(_growth_claim(),),
        gaps=(Gap(element="R_EX_o2_e", kind=GapKind.MEDIUM, detail="unstated", load_bearing=False),),
    )
    problems = validate_constraint_based(ill_formed)
    assert any("must be load-bearing" in p for p in problems)


def test_requires_an_adopted_validating_model() -> None:
    no_model = Dossier(entry="e", claims=(_growth_claim(),))
    assert any("must adopt an SBML" in p for p in validate_constraint_based(no_model))

    unvalidated = Dossier(
        entry="e", claims=(_growth_claim(),),
        artifacts=(ModelArtifact(filename="m.xml", detected_format="sbml-fbc", validates=False),),
    )
    assert any("must validate" in p for p in validate_constraint_based(unvalidated))


def test_requires_a_single_valued_numeric_objective_claim() -> None:
    no_claim = Dossier(entry="e", artifacts=(_adopted_model(),))
    assert any("at least one objective-value claim" in p for p in validate_constraint_based(no_claim))

    figure_claim = DossierClaim(
        id="c", quantity="growth", conditions="", source_location="Fig 3",
        reference_kind=ReferenceKind.DIGITIZED_FIGURE, reference_data=(0.87,),
    )
    dossier = Dossier(entry="e", artifacts=(_adopted_model(),), claims=(figure_claim,))
    assert any("exactly one numeric reference value" in p for p in validate_constraint_based(dossier))


def test_builder_raises_on_an_ill_formed_dossier() -> None:
    with pytest.raises(ValueError, match="ill-formed constraint-based dossier"):
        constraint_based_dossier("e", model=_adopted_model(), objective_claims=[])


# --- End-to-end certification (needs the engine + fba extras) --------------------------------

pytestmark_engine = pytest.mark.skipif(
    importlib.util.find_spec("libsbml") is None or importlib.util.find_spec("scipy") is None,
    reason="the 'engine' (python-libsbml) and 'fba' (scipy) extras are not installed",
)


@pytestmark_engine
def test_certifies_the_known_growth_rate_end_to_end() -> None:
    from reprolith import (
        EnginePin,
        OverallVerdict,
        PaperIdentity,
        Verdict,
        certify_constraint_based,
    )

    dossier = constraint_based_dossier(
        "bigg-e_coli_core", model=_adopted_model(),
        objective_claims=[_growth_claim()], medium=_glucose_aerobic_medium(),
    )
    cert = certify_constraint_based(
        dossier, sbml=_MODEL_PATH.read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core", doi="10.1128/ecosalplus.10.2.1"),
        engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
    )
    assert cert.overall is OverallVerdict.REPRODUCED
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    assert not assessment.assumption_qualified
    assert cert.gap_report == ()


@pytestmark_engine
def test_the_medium_is_genuinely_load_bearing() -> None:
    # The same network, same objective — only the medium changed (oxygen shut off) — reproduces a
    # very different growth rate, which is exactly why the medium is a first-class, load-bearing
    # dossier element rather than an implementation detail.
    from reprolith import ingest_fbc_sbml, solve_objective

    model = ingest_fbc_sbml(_MODEL_PATH.read_text(encoding="utf-8"))
    aerobic = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    assert aerobic == pytest.approx(_KNOWN_GROWTH_RATE, abs=1e-4)

    anaerobic_lower = list(model.lower)
    anaerobic_lower[model.reaction_index("R_EX_o2_e")] = 0.0
    anaerobic = solve_objective(model.stoichiometry, model.objective, anaerobic_lower, model.upper)
    assert anaerobic < 0.3 < aerobic
