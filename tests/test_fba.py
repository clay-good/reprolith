"""The constraint-based (FBA) oracle: LP objective reproduction (spec: constraint-based-class).

Needs the optional ``fba`` extra (scipy); the module skips without it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    Attribution,
    EnginePin,
    FailureMode,
    Fault,
    FbaModel,
    InfeasibleFba,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    build_certificate,
    compare_frog,
    essentiality_agreement,
    flux_variability,
    frog_fingerprint,
    gene_essentiality,
    judge_fingerprint,
    judge_flux,
    judge_objective,
    reaction_essentiality,
    solve_objective,
    synthetic_lethal_genes,
    synthetic_lethal_reactions,
)

# A tiny network: v_in -> A -> v_out(objective). Steady state on A means v_in = v_out; the
# objective (v_out) is capped by v_in's upper bound of 8, so the optimum is 8.
_S = [[1.0, -1.0]]  # one metabolite A, two reactions (v_in, v_out)
_OBJECTIVE = [0.0, 1.0]  # maximize v_out
_LOWER = [0.0, 0.0]
_UPPER = [8.0, None]


def test_solves_the_objective_optimum() -> None:
    assert solve_objective(_S, _OBJECTIVE, _LOWER, _UPPER) == pytest.approx(8.0)


def test_reported_objective_reproduces_and_perturbed_fails() -> None:
    good = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=8.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
    )
    assert good.verdict is Verdict.REPRODUCED

    bad = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=4.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
        attribution=Attribution(mode=FailureMode.MANUSCRIPT_ERROR, implicated="reported objective",
                                fault=Fault.MANUSCRIPT),
    )
    assert bad.verdict is Verdict.FAILED


def test_fba_assessment_feeds_the_certificate() -> None:
    assessment = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=8.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
    )
    cert = build_certificate(
        paper=PaperIdentity(title="An FBA model"),
        engine_pin=EnginePin(engine="scipy-highs", version="1.x"),
        assessments=[assessment],
    )
    assert cert.overall is OverallVerdict.REPRODUCED  # the shared certificate contract is reused


def test_infeasible_problem_raises() -> None:
    # Force infeasibility: v_out lower-bounded above what v_in can supply.
    with pytest.raises(InfeasibleFba):
        solve_objective(_S, _OBJECTIVE, [0.0, 20.0], [8.0, None])


def test_both_reactions_are_essential() -> None:
    # In v_in -> A -> v_out, knocking out either reaction starves the objective, so both
    # reactions are essential.
    assert reaction_essentiality(_S, _OBJECTIVE, _LOWER, _UPPER) == frozenset({0, 1})


def test_a_redundant_reaction_is_not_essential() -> None:
    # Add a second inflow v_in2 -> A. Now either inflow alone can feed v_out (its bound is 8),
    # so neither inflow is essential on its own; only the single outflow remains essential.
    stoich = [[1.0, 1.0, -1.0]]  # v_in, v_in2, v_out
    objective = [0.0, 0.0, 1.0]
    lower = [0.0, 0.0, 0.0]
    upper: list[float | None] = [8.0, 8.0, None]
    assert reaction_essentiality(stoich, objective, lower, upper) == frozenset({2})


def test_a_redundant_pair_is_synthetic_lethal_though_neither_is_essential() -> None:
    # The same two-inflow network. By construction the inflows back each other up: neither is
    # essential singly (see the test above), yet deleting BOTH starves the objective. So single
    # deletion finds no lethality here, while double deletion pinpoints the redundant pair — the
    # exact case synthetic-lethal analysis exists to catch.
    stoich = [[1.0, 1.0, -1.0]]  # v_in, v_in2, v_out
    objective = [0.0, 0.0, 1.0]
    lower = [0.0, 0.0, 0.0]
    upper: list[float | None] = [8.0, 8.0, None]

    assert reaction_essentiality(stoich, objective, lower, upper) == frozenset({2})
    assert synthetic_lethal_reactions(stoich, objective, lower, upper) == frozenset(
        {frozenset({0, 1})}
    )


def test_no_synthetic_lethal_pairs_when_a_single_path_carries_everything() -> None:
    # In the strictly linear v_in -> A -> v_out both reactions are already single-essential, so no
    # pair is *synthetically* lethal — the lethality is single-deletion knowledge, not epistasis.
    assert synthetic_lethal_reactions(_S, _OBJECTIVE, _LOWER, _UPPER) == frozenset()


def test_essentiality_agreement_scores_overlap() -> None:
    assert essentiality_agreement(frozenset({0, 1}), frozenset({0, 1})) == pytest.approx(1.0)
    assert essentiality_agreement(frozenset({0, 1}), frozenset({0, 2})) == pytest.approx(1 / 3)
    assert essentiality_agreement(frozenset(), frozenset()) == pytest.approx(1.0)


def test_fva_pins_a_forced_flux() -> None:
    # In the linear chain, steady state forces v_in = v_out = 8 at the optimum, so FVA reports
    # each as a single pinned value — a claim on either flux could be certified exactly.
    ranges = flux_variability(_S, _OBJECTIVE, _LOWER, _UPPER)
    assert ranges[0] == pytest.approx((8.0, 8.0))
    assert ranges[1] == pytest.approx((8.0, 8.0))


def test_fva_reports_the_alternate_optima_range() -> None:
    # v_in -> A, then two parallel routes A -> B (r1, r2), then B -> v_out (objective). The
    # optimum (10) is achieved by any split r1 + r2 = 10, so FVA honestly reports each parallel
    # flux as the whole interval [0, 10] rather than committing to one ambiguous value.
    stoich = [
        [1.0, -1.0, -1.0, 0.0],  # A: v_in - r1 - r2
        [0.0, 1.0, 1.0, -1.0],  # B: r1 + r2 - v_out
    ]
    objective = [0.0, 0.0, 0.0, 1.0]
    lower = [0.0, 0.0, 0.0, 0.0]
    upper: list[float | None] = [10.0, None, None, None]

    ranges = flux_variability(stoich, objective, lower, upper)
    assert ranges[0] == pytest.approx((10.0, 10.0))  # inflow forced
    assert ranges[1] == pytest.approx((0.0, 10.0))  # parallel route — free within the optimum
    assert ranges[2] == pytest.approx((0.0, 10.0))
    assert ranges[3] == pytest.approx((10.0, 10.0))  # objective outflow forced


def test_judge_flux_reproduces_a_pinned_flux() -> None:
    # A flux the model pins to a single value, matching the report, is a clean reproduction.
    a = judge_flux(
        claim_id="v_out", quantity="outflow at optimum", source_location="Table 2",
        reported=10.0, interval=(10.0, 10.0),
    )
    assert a.verdict is Verdict.REPRODUCED


def test_judge_flux_abstains_when_not_uniquely_determined() -> None:
    # The report sits inside a wide FVA interval: the model is consistent with it but does not
    # pin it, so the honest verdict is abstain, not a pass (design goal 2).
    a = judge_flux(
        claim_id="r1", quantity="parallel-route flux", source_location="Table 2",
        reported=5.0, interval=(0.0, 10.0),
    )
    assert a.verdict is Verdict.NOT_EVALUABLE
    assert "does not uniquely determine" in (a.root_cause or "")


def test_judge_flux_fails_when_outside_the_feasible_range() -> None:
    # A reported flux the model cannot reach at the optimum fails, judged against the nearest
    # feasible value; like any non-pass it must carry a root-cause attribution.
    a = judge_flux(
        claim_id="r1", quantity="parallel-route flux", source_location="Table 2",
        reported=25.0, interval=(0.0, 10.0),
        attribution=Attribution(mode=FailureMode.MANUSCRIPT_ERROR, implicated="reported flux",
                                fault=Fault.MANUSCRIPT),
    )
    assert a.verdict is Verdict.FAILED


def test_fba_failure_carries_a_constraint_based_root_cause() -> None:
    # A failed FBA verdict can be attributed with a first-class constraint-based category
    # (here, an unspecified medium) rather than borrowing a PK/PD root cause.
    a = judge_objective(
        claim_id="obj", quantity="max growth flux", source_location="Table 1",
        reported=4.0, stoichiometry=_S, objective=_OBJECTIVE, lower=_LOWER, upper=_UPPER,
        attribution=Attribution(mode=FailureMode.UNSPECIFIED_MEDIUM,
                                implicated="exchange bounds", fault=Fault.MANUSCRIPT),
    )
    assert a.verdict is Verdict.FAILED
    assert a.root_cause == "unspecified-medium-or-exchange-bounds"


_MODEL = FbaModel(
    species_ids=("A",),
    reaction_ids=("v_in", "v_out"),
    stoichiometry=((1.0, -1.0),),
    objective=(0.0, 1.0),
    lower=(0.0, 0.0),
    upper=(8.0, None),
)


def test_frog_fingerprint_bundles_the_three_components() -> None:
    fp = frog_fingerprint(_MODEL)
    assert fp.objective_value == pytest.approx(8.0)
    assert fp.variability == ((8.0, 8.0), (8.0, 8.0))  # both fluxes forced at the optimum
    # Deleting either reaction starves the objective, so each deletion optimum is 0.
    assert fp.deletion_objectives == pytest.approx((0.0, 0.0))


def test_frog_comparison_agrees_with_itself() -> None:
    fp = frog_fingerprint(_MODEL)
    result = compare_frog(fp, fp)
    assert result.agrees
    assert result.disagreements == ()


def test_frog_comparison_names_a_perturbed_objective() -> None:
    computed = frog_fingerprint(_MODEL)
    # A curated fingerprint reporting a different objective value must fail on that component,
    # with the disagreement named, not hidden behind an overall pass.
    reported = frog_fingerprint(
        FbaModel(
            species_ids=("A",), reaction_ids=("v_in", "v_out"),
            stoichiometry=((1.0, -1.0),), objective=(0.0, 1.0),
            lower=(0.0, 0.0), upper=(5.0, None),  # tighter inflow -> optimum 5, not 8
        )
    )
    result = compare_frog(computed, reported)
    assert not result.agrees
    assert not result.objective_agrees
    assert any("objective" in d for d in result.disagreements)


def test_judge_fingerprint_reproduces_on_agreement() -> None:
    fp = frog_fingerprint(_MODEL)
    a = judge_fingerprint(
        claim_id="frog", quantity="FROG fingerprint", source_location="curation",
        comparison=compare_frog(fp, fp),
    )
    assert a.verdict is Verdict.REPRODUCED
    assert a.method == "fingerprint-comparison"


def test_judge_fingerprint_fails_with_named_disagreements() -> None:
    computed = frog_fingerprint(_MODEL)
    reported = frog_fingerprint(
        FbaModel(
            species_ids=("A",), reaction_ids=("v_in", "v_out"),
            stoichiometry=((1.0, -1.0),), objective=(0.0, 1.0),
            lower=(0.0, 0.0), upper=(5.0, None),
        )
    )
    a = judge_fingerprint(
        claim_id="frog", quantity="FROG fingerprint", source_location="curation",
        comparison=compare_frog(computed, reported),
        attribution=Attribution(mode=FailureMode.AMBIGUOUS_OBJECTIVE,
                                implicated="objective bound", fault=Fault.RECONSTRUCTION),
    )
    assert a.verdict is Verdict.FAILED
    assert a.discrepancy and "objective" in a.discrepancy  # the disagreement is recorded, auditable


# A gene-annotated version of the tiny network: v_in is run by *isozymes* (either gene suffices),
# and v_out — the only objective-bearing reaction — needs a two-gene *complex* (both required).
_GENE_MODEL = FbaModel(
    species_ids=("A",),
    reaction_ids=("v_in", "v_out"),
    stoichiometry=((1.0, -1.0),),
    objective=(0.0, 1.0),
    lower=(0.0, 0.0),
    upper=(8.0, None),
    gene_associations=(("v_in", ("or", ("g1", "g2"))), ("v_out", ("and", ("g3", "g4")))),
)


def test_model_lists_its_genes_in_a_deterministic_order() -> None:
    assert _GENE_MODEL.genes() == ("g1", "g2", "g3", "g4")


def test_gene_essentiality_respects_and_or_rules() -> None:
    # The OR on v_in makes each isozyme dispensable; the AND on the objective reaction makes both
    # subunits of the complex essential — the whole point of reading GPR rules rather than guessing.
    assert gene_essentiality(_GENE_MODEL) == frozenset({"g3", "g4"})


def test_isozyme_genes_are_synthetic_lethal_though_neither_is_essential() -> None:
    # v_in is gated by (g1 OR g2): each isozyme is dispensable alone (the other carries the flux),
    # so gene essentiality misses them. Deleting BOTH knocks out v_in and starves the objective, so
    # {g1, g2} is the one synthetic-lethal gene pair — the case gene double-deletion exists to catch.
    # (g3/g4 are single-essential via the AND, so they form no *synthetic* pair.)
    assert synthetic_lethal_genes(_GENE_MODEL) == frozenset({frozenset({"g1", "g2"})})


def test_essentiality_agreement_scores_gene_label_sets() -> None:
    # The same Jaccard agreement serves gene labels (str), not only reaction indices (int), so a
    # computed gene-essential set can be scored against a reported one.
    computed = gene_essentiality(_GENE_MODEL)  # {"g3", "g4"}
    assert essentiality_agreement(computed, frozenset({"g3", "g4"})) == pytest.approx(1.0)
    assert essentiality_agreement(computed, frozenset({"g3", "g9"})) == pytest.approx(1 / 3)


def test_frog_fingerprint_includes_the_gene_deletion_section() -> None:
    fp = frog_fingerprint(_GENE_MODEL)
    assert fp.gene_ids == ("g1", "g2", "g3", "g4")
    # Deleting an isozyme leaves the optimum untouched; deleting a complex subunit collapses it.
    assert fp.gene_deletion_objectives == pytest.approx((8.0, 8.0, 0.0, 0.0))


def test_frog_comparison_names_a_gene_deletion_disagreement() -> None:
    computed = frog_fingerprint(_GENE_MODEL)
    # A curation that models v_out as isozymes (OR) instead of a complex (AND): the same genes are
    # present, but deleting g3 or g4 no longer collapses growth, so the gene section must disagree.
    reported = frog_fingerprint(
        FbaModel(
            species_ids=("A",), reaction_ids=("v_in", "v_out"),
            stoichiometry=((1.0, -1.0),), objective=(0.0, 1.0), lower=(0.0, 0.0), upper=(8.0, None),
            gene_associations=(("v_in", ("or", ("g1", "g2"))), ("v_out", ("or", ("g3", "g4")))),
        )
    )
    result = compare_frog(computed, reported)
    assert not result.agrees
    assert not result.gene_deletion_agrees
    assert any("gene-deletion g3" in d for d in result.disagreements)


def test_frog_comparison_names_a_gene_present_in_only_one_fingerprint() -> None:
    computed = frog_fingerprint(_GENE_MODEL)  # genes g1, g2, g3, g4
    # A curation whose objective reaction is controlled by a single, different gene: g3 and g4 are
    # absent from it, so a structural gene mismatch must be named, not hidden behind a numeric pass.
    reported = frog_fingerprint(
        FbaModel(
            species_ids=("A",), reaction_ids=("v_in", "v_out"),
            stoichiometry=((1.0, -1.0),), objective=(0.0, 1.0), lower=(0.0, 0.0), upper=(8.0, None),
            gene_associations=(("v_in", ("or", ("g1", "g2"))), ("v_out", "g5")),
        )
    )
    result = compare_frog(computed, reported)
    assert not result.agrees
    assert not result.gene_deletion_agrees
    assert any("gene g3 present in only one fingerprint" in d for d in result.disagreements)
    assert any("gene g5 present in only one fingerprint" in d for d in result.disagreements)


def test_frog_comparison_names_a_reaction_present_in_only_one_fingerprint() -> None:
    computed = frog_fingerprint(_MODEL)  # reactions v_in, v_out
    # A curation with an extra drain reaction the computed model lacks: the structural mismatch must
    # be named and must fail the variability/deletion components, not pass on the shared reactions.
    reported = frog_fingerprint(
        FbaModel(
            species_ids=("A",), reaction_ids=("v_in", "v_out", "v_leak"),
            stoichiometry=((1.0, -1.0, -1.0),), objective=(0.0, 1.0, 0.0),
            lower=(0.0, 0.0, 0.0), upper=(8.0, None, None),
        )
    )
    result = compare_frog(computed, reported)
    assert not result.agrees
    assert not result.variability_agrees and not result.deletion_agrees
    assert any("reaction v_leak present in only one fingerprint" in d for d in result.disagreements)
