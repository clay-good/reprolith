"""A reported essential set can be certified, and the lethality cutoff is measured, not assumed.

`gene_essentiality` and `reaction_essentiality` have been in this class since it was written, and
both are cross-validated element-for-element against COBRApy — the essential genes and reactions of
*E. coli* core are committed reference data. No claim could carry one, so the second-most-reported
constraint-based result after a growth rate, and the one a genome-scale paper validates against
experimental knockout data, was implemented and unreachable.

The judgement call this file is really about is the **cutoff**. "Essential" means "growth falls
below X", and the two conventions in use — a millionth of wild type, and 1% of it — are different
sets on the same model. Neither is wrong. So a claim that states its cutoff is judged at it, and one
that does not has the difference computed rather than qualified on principle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")

from reprolith import ingest_fbc_sbml  # noqa: E402
from reprolith.constraint_based import EssentialityClaim, _cutoff_assumption  # noqa: E402
from reprolith.enums import Verdict  # noqa: E402
from reprolith.fba import (  # noqa: E402
    EssentialKind,
    FbaModel,
    ReportedEssentialSet,
    essential_set,
    essentiality_threshold_sensitivity,
    judge_essentiality,
)
from reprolith.oracle import ComparisonMethod, undetermined_shortfall  # noqa: E402

_DIR = Path(__file__).parent.parent / "datasets" / "constraint_based"
_REFERENCE = json.loads(
    (_DIR / "cross_validation" / "e_coli_core_essentiality.json").read_text(encoding="utf-8")
)


def _model() -> FbaModel:
    return ingest_fbc_sbml((_DIR / "e_coli_core.xml").read_text(encoding="utf-8"))


def _judge(reported: ReportedEssentialSet, model: FbaModel | None = None):
    return judge_essentiality(
        claim_id="essential", quantity="essential genes", source_location="Table 2",
        reported=reported, model=model if model is not None else _model(),
        # What the front end supplies, so a miss here is published as an uncategorized shortfall
        # rather than raising: the shared contract refuses a non-pass carrying no root cause.
        attribution=undetermined_shortfall("essential genes"),
    )


# --- the set, judged element for element ---------------------------------------------------------


def test_the_reference_essential_gene_set_reproduces() -> None:
    # COBRApy's own single-gene-deletion answer for this model, committed as reference data.
    assessment = _judge(ReportedEssentialSet(
        kind=EssentialKind.GENES, ids=tuple(_REFERENCE["essential_genes"])
    ))
    assert assessment.verdict is Verdict.REPRODUCED
    assert assessment.method == ComparisonMethod.ESSENTIAL_SET_MATCH.value
    assert "all 7 essential genes reproduced" in assessment.discrepancy


def test_a_missing_gene_is_named_rather_than_counted() -> None:
    # The strong form of the comparison: a set that is one gene short does not reproduce, and the
    # discrepancy says which gene and how far apart the two sets are.
    short = tuple(g for g in _REFERENCE["essential_genes"] if g != "b0720")
    assessment = _judge(ReportedEssentialSet(kind=EssentialKind.GENES, ids=short))
    assert assessment.verdict is Verdict.FAILED
    assert "1 essential here and not reported (b0720)" in assessment.discrepancy
    assert "agreement 0.857 of the union" in assessment.discrepancy


def test_a_reported_set_of_the_right_size_and_the_wrong_members_fails() -> None:
    # The reason a count is not a set: seven genes, none of them the model's.
    wrong = tuple(f"b{i:04d}" for i in range(7))
    assessment = _judge(ReportedEssentialSet(kind=EssentialKind.GENES, ids=wrong))
    assert assessment.verdict is Verdict.FAILED
    assert "agreement 0.000 of the union" in assessment.discrepancy


# --- the count, named as the weaker comparison it is ---------------------------------------------


def test_a_reported_count_is_judged_as_a_count_and_says_so() -> None:
    assessment = _judge(ReportedEssentialSet(kind=EssentialKind.GENES, count=7))
    assert assessment.verdict is Verdict.REPRODUCED
    # Not a set match: a certificate that called this one would claim more than it checked.
    assert assessment.method == ComparisonMethod.ESSENTIAL_COUNT_MATCH.value
    assert assessment.tolerance == "exact match on the number of essential genes"


def test_the_count_form_passes_where_the_set_form_fails() -> None:
    # The distinction, in one model: seven genes that are not the model's satisfy the count and
    # fail the set. This is why the two comparisons carry different names.
    wrong = tuple(f"b{i:04d}" for i in range(7))
    assert _judge(ReportedEssentialSet(kind=EssentialKind.GENES, count=7)).verdict is (
        Verdict.REPRODUCED
    )
    assert _judge(ReportedEssentialSet(kind=EssentialKind.GENES, ids=wrong)).verdict is (
        Verdict.FAILED
    )


# --- reactions ------------------------------------------------------------------------------------


def test_the_reference_essential_reaction_set_reproduces_under_the_model_s_own_ids() -> None:
    # COBRApy strips the SBML `R_` prefix and this package keeps it, which is the identifier trap
    # the FROG comparison already had to learn: aligning without knowing it reports every reaction
    # as present on one side only. The certificate judges the ids the *model* states.
    reported = tuple(f"R_{r}" for r in _REFERENCE["essential_reactions"])
    assessment = _judge(ReportedEssentialSet(kind=EssentialKind.REACTIONS, ids=reported))
    assert assessment.verdict is Verdict.REPRODUCED
    assert "all 18 essential reactions reproduced" in assessment.discrepancy


def test_the_unprefixed_ids_do_not_silently_match() -> None:
    unprefixed = tuple(_REFERENCE["essential_reactions"])
    assessment = _judge(ReportedEssentialSet(kind=EssentialKind.REACTIONS, ids=unprefixed))
    assert assessment.verdict is Verdict.FAILED


# --- a model that cannot be asked the question ---------------------------------------------------


def test_a_gene_claim_on_a_model_with_no_gene_rules_abstains() -> None:
    model = FbaModel(
        species_ids=("A",), reaction_ids=("R1",), stoichiometry=((1.0,),),
        objective=(1.0,), lower=(0.0,), upper=(10.0,),
    )
    assessment = _judge(ReportedEssentialSet(kind=EssentialKind.GENES, ids=("b0001",)), model)
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "no gene-protein-reaction rules" in assessment.root_cause


# --- the cutoff -----------------------------------------------------------------------------------


def test_the_cutoff_choice_is_measured_and_costs_this_model_nothing() -> None:
    # Every gene lethal at a millionth of wild-type growth is lethal at 1% of it on this model, so
    # the choice provably cannot move the verdict — and no assumption is minted for it. Qualifying
    # it anyway would downgrade a certificate for a decision that does not matter here.
    sensitivity = essentiality_threshold_sensitivity(_model(), EssentialKind.GENES)
    assert sensitivity["agree"] is True
    assert sensitivity["size"] == sensitivity["other_size"] == 7
    claim = EssentialityClaim(
        claim_id="essential", quantity="essential genes", source_location="Table 2",
        reported=ReportedEssentialSet(kind=EssentialKind.GENES, count=7),
    )
    assert _cutoff_assumption(claim, _model()) is None


def test_a_stated_cutoff_is_used_and_earns_no_assumption() -> None:
    claim = EssentialityClaim(
        claim_id="essential", quantity="essential genes", source_location="Table 2",
        reported=ReportedEssentialSet(kind=EssentialKind.GENES, count=7, threshold=0.01),
    )
    assert claim.reported.cutoff == 0.01
    assert claim.reported.cutoff_is_reprolith_s is False
    assert _cutoff_assumption(claim, _model()) is None


def test_a_cutoff_that_changes_the_set_is_qualified_for() -> None:
    # A model where the two conventions disagree: one reaction whose knockout leaves 0.5% of
    # wild-type growth is near-lethal at a millionth and lethal at 1%, which is exactly what the
    # convention exists to catch. The engine's default is used and the certificate says so.
    model = FbaModel(
        species_ids=(), reaction_ids=("main", "bypass", "biomass"),
        # An unconstrained model: `main` carries flux 10, `bypass` at most 0.05, and biomass is
        # whichever is available — so deleting `main` leaves 0.5% of the optimum.
        stoichiometry=((0.0, 0.0, 0.0),),
        objective=(0.0, 0.0, 1.0), lower=(0.0, 0.0, 0.0), upper=(10.0, 0.05, None),
    )
    # Biomass is bounded by the sum of the two routes, expressed as a mass balance.
    model = FbaModel(
        species_ids=("hub",), reaction_ids=("main", "bypass", "biomass"),
        stoichiometry=((1.0, 1.0, -1.0),),
        objective=(0.0, 0.0, 1.0), lower=(0.0, 0.0, 0.0), upper=(10.0, 0.05, None),
    )
    sensitivity = essentiality_threshold_sensitivity(model, EssentialKind.REACTIONS)
    assert sensitivity["agree"] is False
    claim = EssentialityClaim(
        claim_id="essential", quantity="essential reactions", source_location="Table 2",
        reported=ReportedEssentialSet(kind=EssentialKind.REACTIONS, count=1),
    )
    assumption = _cutoff_assumption(claim, model)
    assert assumption is not None
    assert assumption.load_bearing and assumption.author_can_close
    assert "near-lethal rather than lethal" in assumption.basis


# --- what the claim refuses -----------------------------------------------------------------------


def test_a_claim_giving_both_a_set_and_a_count_is_refused() -> None:
    with pytest.raises(ValueError, match="exactly one of"):
        ReportedEssentialSet(kind=EssentialKind.GENES, ids=("b0720",), count=1)


def test_a_repeated_id_is_refused_rather_than_counted_twice() -> None:
    with pytest.raises(ValueError, match="names the same element twice"):
        ReportedEssentialSet(kind=EssentialKind.GENES, ids=("b0720", "b0720"))


def test_a_cutoff_outside_zero_and_one_is_refused() -> None:
    with pytest.raises(ValueError, match="fraction of unperturbed growth"):
        ReportedEssentialSet(kind=EssentialKind.GENES, count=7, threshold=5.0)


def test_the_essential_set_helper_answers_in_the_model_s_ids() -> None:
    # `reaction_essentiality` answers in column indices, which is what the solver works in and not
    # what a paper reports. A caller re-deriving that mapping is a caller who can get it wrong.
    ids = essential_set(_model(), EssentialKind.REACTIONS)
    assert all(isinstance(i, str) for i in ids)
    assert "R_CS" in ids
