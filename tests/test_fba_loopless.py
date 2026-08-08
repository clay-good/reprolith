"""Loopless FVA removes thermodynamically infeasible internal-loop flux (Schellenberger 2011).

The ground truth here is analytical, not borrowed from another tool: a three-reaction cycle
A→B→C→A satisfies the mass balance for any flux ``t`` yet has no net thermodynamic driving force,
so a physically realizable distribution must set that cycle to zero. Standard FVA cannot see this
and reports the inflated range; loopless FVA must collapse it to the value hand-derivable from the
network. A model with no internal cycle is the control: loopless FVA has nothing to remove and must
reproduce standard FVA exactly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("scipy")

from reprolith import (  # noqa: E402
    Verdict,
    flux_variability,
    judge_flux,
    loopless_flux_variability,
)

# Metabolites [A, B, C]; reactions [EX_A, EX_C, R1: A→B, R2: B→C, R3: C→A].
# EX_A imports A (≤10), EX_C exports C, and R1·R2·R3 close an internal loop. The only productive
# route is EX_A → R1 → R2 → EX_C, so the optimum export is exactly the import cap, 10.
_LOOP_S = [
    [1.0, 0.0, -1.0, 0.0, 1.0],  # A: +EX_A −R1 +R3
    [0.0, 0.0, 1.0, -1.0, 0.0],  # B: +R1 −R2
    [0.0, -1.0, 0.0, 1.0, -1.0],  # C: −EX_C +R2 −R3
]
_LOOP_OBJECTIVE = [0.0, 1.0, 0.0, 0.0, 0.0]  # maximize EX_C
_LOOP_LOWER = [0.0, 0.0, 0.0, 0.0, 0.0]
_LOOP_UPPER: list[float | None] = [10.0, 1000.0, 1000.0, 1000.0, 1000.0]


def test_standard_fva_reports_the_spurious_internal_loop_flux() -> None:
    """Without the loop law, R1/R2 range up to their bound and R3 (a pure cycle reaction) with them."""
    ranges = flux_variability(_LOOP_S, _LOOP_OBJECTIVE, _LOOP_LOWER, _LOOP_UPPER)
    ex_a, ex_c, r1, r2, r3 = ranges
    # The productive boundary is pinned; only the loop lets internal reactions roam.
    assert ex_a == pytest.approx((10.0, 10.0), abs=1e-6)
    assert ex_c == pytest.approx((10.0, 10.0), abs=1e-6)
    # The cycle inflates every internal reaction: R1/R2 run 10 + t, R3 runs t, up to the 1000 bound.
    assert r1[1] == pytest.approx(1000.0, abs=1e-4)
    assert r2[1] == pytest.approx(1000.0, abs=1e-4)
    assert r3[1] == pytest.approx(990.0, abs=1e-4)


def test_loopless_fva_collapses_the_cycle_to_its_thermodynamic_range() -> None:
    """The loop law forces R3 (pure cycle) to 0 and pins R1/R2 to the productive flux, 10."""
    ranges = loopless_flux_variability(_LOOP_S, _LOOP_OBJECTIVE, _LOOP_LOWER, _LOOP_UPPER)
    ex_a, ex_c, r1, r2, r3 = ranges
    assert ex_a == pytest.approx((10.0, 10.0), abs=1e-5)
    assert ex_c == pytest.approx((10.0, 10.0), abs=1e-5)
    assert r1 == pytest.approx((10.0, 10.0), abs=1e-5)
    assert r2 == pytest.approx((10.0, 10.0), abs=1e-5)
    assert r3 == pytest.approx((0.0, 0.0), abs=1e-5)


def test_loopless_fva_reactions_subset_matches_the_full_computation() -> None:
    """The ``reactions`` subset returns exactly the requested indices, in order, with full-run values."""
    full = loopless_flux_variability(_LOOP_S, _LOOP_OBJECTIVE, _LOOP_LOWER, _LOOP_UPPER)
    # Ask for R3 (a pure cycle) then R1 (productive), deliberately out of order.
    subset = loopless_flux_variability(
        _LOOP_S, _LOOP_OBJECTIVE, _LOOP_LOWER, _LOOP_UPPER, reactions=[4, 2]
    )
    assert len(subset) == 2
    assert subset[0] == pytest.approx(full[4], abs=1e-6)  # R3
    assert subset[1] == pytest.approx(full[2], abs=1e-6)  # R1


def test_loopless_fva_equals_standard_fva_on_a_loop_free_model() -> None:
    """With no internal cycle the null space is trivial: loopless FVA must reproduce standard FVA."""
    # Drop R3, so R1/R2 no longer close a loop; the network is a straight chain A→B→C.
    stoichiometry = [
        [1.0, 0.0, -1.0, 0.0],  # A
        [0.0, 0.0, 1.0, -1.0],  # B
        [0.0, -1.0, 0.0, 1.0],  # C
    ]
    objective = [0.0, 1.0, 0.0, 0.0]
    lower = [0.0, 0.0, 0.0, 0.0]
    upper: list[float | None] = [10.0, 1000.0, 1000.0, 1000.0]
    standard = flux_variability(stoichiometry, objective, lower, upper)
    loopless = loopless_flux_variability(stoichiometry, objective, lower, upper)
    for (s_lo, s_hi), (l_lo, l_hi) in zip(standard, loopless):
        assert l_lo == pytest.approx(s_lo, abs=1e-6)
        assert l_hi == pytest.approx(s_hi, abs=1e-6)


def test_loop_inflation_forces_a_false_abstention_that_loopless_fva_resolves() -> None:
    """The honesty payoff, end to end through ``judge_flux``.

    R1's true flux is exactly 10, and the paper reports 10. Plain FVA's loop-inflated interval
    [10, 1000] does not *pin* R1, so ``judge_flux`` must abstain — it cannot certify a value the
    (artifactual) alternate optima leave free. Under loopless FVA the interval collapses to [10, 10],
    so the same reported value is now a clean reproduction. The loop artifact was the sole cause of
    the abstention.
    """
    r1_index = 2
    reported = 10.0
    plain = flux_variability(_LOOP_S, _LOOP_OBJECTIVE, _LOOP_LOWER, _LOOP_UPPER)[r1_index]
    loopless = loopless_flux_variability(_LOOP_S, _LOOP_OBJECTIVE, _LOOP_LOWER, _LOOP_UPPER)[r1_index]

    plain_verdict = judge_flux(
        claim_id="R1", quantity="A→B flux at optimum", source_location="Table 1",
        reported=reported, interval=plain,
    )
    loopless_verdict = judge_flux(
        claim_id="R1", quantity="A→B flux at optimum", source_location="Table 1",
        reported=reported, interval=loopless,
    )
    assert plain_verdict.verdict is Verdict.NOT_EVALUABLE
    assert loopless_verdict.verdict is Verdict.REPRODUCED


# --- Real-model validation: the E. coli core FRD7/SUCDi thermodynamically infeasible loop ---
#
# Ground truth is documented and independent of this engine: fumarate reductase (FRD7) and succinate
# dehydrogenase (SUCDi) form the textbook infeasible loop of the E. coli core model (Orth, Thiele &
# Palsson 2010; the canonical example of the loopless-FBA literature, Schellenberger et al. 2011).
# At the aerobic growth optimum SUCDi carries a specific TCA-cycle flux and FRD7 is off, so their
# plain-FVA ranges reaching ~1000 (the default bound) are pure loop artifacts, not real flexibility.

_MODEL = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"


def _core_model():
    from reprolith.sbml import ingest_fbc_sbml

    return ingest_fbc_sbml(_MODEL.read_text(encoding="utf-8"))


def test_loopless_fva_removes_the_e_coli_core_frd7_sucdi_loop() -> None:
    pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")
    model = _core_model()
    args = (model.stoichiometry, model.objective, model.lower, model.upper)
    standard = flux_variability(*args, fraction_of_optimum=1.0)
    loopless = loopless_flux_variability(*args, fraction_of_optimum=1.0)

    sucdi = model.reaction_ids.index("R_SUCDi")
    frd7 = model.reaction_ids.index("R_FRD7")
    # Plain FVA shows the loop: both reactions can run to (near) the ±1000 bound.
    assert standard[sucdi][1] > 900.0
    assert standard[frd7][1] > 900.0
    # Loopless FVA strips the artifact: neither reaction's optimal range comes near that bound.
    assert loopless[sucdi][1] < 100.0
    assert loopless[frd7][1] < 100.0

    # The exact invariant across the whole model: adding the loop law can only shrink a range, never
    # widen it, so every loopless interval is contained in the standard one.
    for (s_lo, s_hi), (l_lo, l_hi) in zip(standard, loopless):
        assert l_lo >= s_lo - 1e-6
        assert l_hi <= s_hi + 1e-6
