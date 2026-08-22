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
def test_the_shipped_worked_example_dossier_reproduces() -> None:
    # The walkable worked-example artifact is a real, reproducible fixture, not just documentation:
    # its stored dossier.json loads and certifies to the reproduced verdict its certificate.txt shows.
    import json

    from reprolith import EnginePin, OverallVerdict, PaperIdentity, certify_constraint_based
    from reprolith.persistence import dossier_from_dict

    worked_example = _MODEL_PATH.parent / "worked_example"
    dossier = dossier_from_dict(json.loads((worked_example / "dossier.json").read_text("utf-8")))
    cert = certify_constraint_based(
        dossier, sbml=_MODEL_PATH.read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core", doi="10.1128/ecosalplus.10.2.1"),
        engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
    )
    assert cert.overall is OverallVerdict.REPRODUCED
    assert "OVERALL: reproduced" in (worked_example / "certificate.txt").read_text("utf-8")


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
def test_an_unstated_load_bearing_medium_never_certifies_a_clean_reproduction() -> None:
    # The honesty invariant, end to end: the model's default bounds happen to reproduce the reported
    # growth rate, but the paper never stated its oxygen uptake — that value was applied as a guess.
    # The certificate must not take clean credit; a load-bearing medium gap qualifies the claim and
    # downgrades the overall verdict to partially-reproduced. (Regression: this path formerly routed
    # the gap into the prose report only, leaving the verdict a clean green `reproduced`.)
    from reprolith import (
        EnginePin,
        OverallVerdict,
        PaperIdentity,
        Verdict,
        certify_constraint_based,
    )

    dossier = constraint_based_dossier(
        "unstated-o2", model=_adopted_model(), objective_claims=[_growth_claim()],
        medium_gaps=[Gap(element="R_EX_o2_e", kind=GapKind.MEDIUM,
                         detail="the paper does not state the oxygen uptake bound",
                         load_bearing=True)],
    )
    cert = certify_constraint_based(
        dossier, sbml=_MODEL_PATH.read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core (unstated medium)", doi=""),
        engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
    )
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.REPRODUCED  # the number matches...
    assert assessment.assumption_qualified  # ...but only under a guessed medium, so it is qualified
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert cert.gap_report and "R_EX_o2_e" in cert.gap_report[0]


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


@pytestmark_engine
def test_certifies_an_honest_not_reproduced_verdict_with_a_root_cause() -> None:
    # A dossier claiming a growth rate the model does not reach must be certifiable as a *failure*,
    # not left uncertifiable: with the required constraint-based root cause supplied, the pathway
    # emits an honest not-reproduced certificate carrying that cause.
    from reprolith import (
        Attribution,
        EnginePin,
        FailureMode,
        Fault,
        OverallVerdict,
        PaperIdentity,
        Verdict,
        certify_constraint_based,
    )

    overclaim = DossierClaim(
        id="overclaimed-growth", quantity="maximal growth rate", conditions="glucose minimal",
        source_location="hypothetical over-report", reference_kind=ReferenceKind.NUMERIC,
        reference_data=(1.5,),  # far above the ~0.874 the model can reach
    )
    dossier = constraint_based_dossier(
        "overclaim", model=_adopted_model(), objective_claims=[overclaim],
        medium=_glucose_aerobic_medium(),
    )
    cert = certify_constraint_based(
        dossier, sbml=_MODEL_PATH.read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core (over-report)", doi=""),
        engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
        shortfalls={"overclaimed-growth": Attribution(
            mode=FailureMode.AMBIGUOUS_OBJECTIVE,
            implicated="reported objective value exceeds the model optimum",
            fault=Fault.MANUSCRIPT)},
    )
    assert cert.overall is OverallVerdict.NOT_REPRODUCED
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.FAILED
    assert assessment.root_cause == "ambiguous-biomass-or-objective-definition"


@pytestmark_engine
def test_a_medium_naming_an_unknown_reaction_is_surfaced_not_ignored() -> None:
    # Adopt-and-verify: a recorded medium that names an exchange the adopted model does not contain
    # is a real mismatch (a typo, or the wrong model), and must raise rather than be silently
    # dropped — otherwise the certificate would be solved under bounds nobody recorded.
    from reprolith import EnginePin, PaperIdentity, certify_constraint_based

    dossier = constraint_based_dossier(
        "mismatch", model=_adopted_model(), objective_claims=[_growth_claim()],
        medium=[Parameter(name="R_EX_not_in_model_e", value=5.0, unit=FLUX_UNIT,
                          source_location="typo")],
    )
    with pytest.raises(ValueError, match="does not contain"):
        certify_constraint_based(
            dossier, sbml=_MODEL_PATH.read_text(encoding="utf-8"),
            paper=PaperIdentity(title="E. coli core", doi=""),
            engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
        )


def test_a_load_bearing_gap_of_any_kind_qualifies_the_verdict() -> None:
    """It used to be only `MEDIUM`, so any other load-bearing gap vanished from the record.

    A gap of another kind — an objective the paper never named — passed validation and then
    reached neither the gap report nor the per-claim qualification, and the certificate published
    a clean unqualified `reproduced`.
    """
    from pathlib import Path

    from reprolith import (
        EnginePin,
        ModelArtifact,
        OverallVerdict,
        PaperIdentity,
        ReferenceKind,
    )
    from reprolith.constraint_based import certify_constraint_based, constraint_based_dossier
    from reprolith.dossier import DossierClaim, Gap, GapKind

    sbml = (
        Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
    ).read_text(encoding="utf-8")
    dossier = constraint_based_dossier(
        "e_coli_core",
        model=ModelArtifact(filename="e_coli_core.xml", detected_format="sbml", validates=True),
        objective_claims=(
            DossierClaim(id="growth", quantity="maximal growth rate", conditions="aerobic",
                         source_location="Table 1", reference_kind=ReferenceKind.NUMERIC,
                         reference_data=(0.8739215,)),
        ),
        medium_gaps=(
            Gap(element="biomass objective", kind=GapKind.OTHER,
                detail="the paper never states which biomass reaction it maximized",
                load_bearing=True),
        ),
    )
    cert = certify_constraint_based(
        paper=PaperIdentity(title="E. coli core", doi=""),
        engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
        dossier=dossier,
        sbml=sbml,
    )
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert any("biomass objective" in note for note in cert.gap_report)
    assert all(a.assumption_qualified for a in cert.assessments)


@pytestmark_engine
def test_certifying_refuses_a_dossier_the_class_calls_ill_formed() -> None:
    """The class's rules were written down in `validate_constraint_based` and never consulted here.

    `certify_constraint_based` read `reference_data[0]` and let the judge default to a NUMERIC
    reference, so a growth rate the dossier records as digitized off a figure was judged at the
    numeric tolerance and then published as `reference_kind: "numeric"` — the certificate asserting
    a precision of reference the paper never gave, and flipping the verdict on it (a relative error
    of 0.1062 is `reproduced` in the digitized band and `not-reproduced` in the numeric one). The
    milestone's own entry reaches certification through `dossier_from_dict`, which validates
    nothing, so guarding the way in left the way out open.
    """
    import dataclasses
    import json

    from reprolith import EnginePin, PaperIdentity, ReferenceKind, certify_constraint_based
    from reprolith.persistence import dossier_from_dict

    worked_example = _MODEL_PATH.parent / "worked_example"
    dossier = dossier_from_dict(json.loads((worked_example / "dossier.json").read_text("utf-8")))
    claims = list(dossier.claims)
    sbml = _MODEL_PATH.read_text(encoding="utf-8")
    pin = EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs")

    for mutated in (
        dataclasses.replace(claims[0], reference_kind=ReferenceKind.DIGITIZED_FIGURE,
                            reference_data=(0.79,)),
        dataclasses.replace(claims[0], reference_data=(0.79, 0.873922)),
    ):
        ill_formed = dataclasses.replace(dossier, claims=tuple([mutated] + claims[1:]))
        with pytest.raises(ValueError, match="exactly one numeric reference value"):
            certify_constraint_based(
                ill_formed, sbml=sbml,
                paper=PaperIdentity(title="E. coli core", doi="10.1128/ecosalplus.10.2.1"),
                engine_pin=pin,
            )
