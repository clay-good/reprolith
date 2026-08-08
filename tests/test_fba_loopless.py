"""Loopless FVA removes thermodynamically infeasible internal-loop flux (Schellenberger 2011).

The ground truth here is analytical, not borrowed from another tool: a three-reaction cycle
A→B→C→A satisfies the mass balance for any flux ``t`` yet has no net thermodynamic driving force,
so a physically realizable distribution must set that cycle to zero. Standard FVA cannot see this
and reports the inflated range; loopless FVA must collapse it to the value hand-derivable from the
network. A model with no internal cycle is the control: loopless FVA has nothing to remove and must
reproduce standard FVA exactly.
"""

from __future__ import annotations

import pytest

pytest.importorskip("scipy")

from reprolith import flux_variability, loopless_flux_variability  # noqa: E402

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
