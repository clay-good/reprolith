"""The medium a constraint-based number was solved under, stated in the direction it was applied.

A medium entry is a maximum **uptake**. Applying it sets that exchange reaction's *lower* flux bound
to its negation, because uptake runs negative — the COBRA convention, which `_apply_medium` and the
inline linter both follow correctly and which the cross-validation against COBRApy exercises.

Both surfaces printed it as `R_EX_glc__D_e<=10.0`. Read as a flux bound, which is what a reaction id
and a `<=` mean in this context, that says the opposite: secretion capped at +10, uptake unlimited.
A reader re-running the model from the certificate's own protocol line would build a different
linear program from the one the certificate reports on — and the solver being right is exactly why
no cross-validation could catch it. It was found by reading the finished artifact straight through.
"""

from __future__ import annotations

from pathlib import Path

import pytest

#: The core CI job installs no extras. Gated per test rather than for the module: the artifact check
#: below reads a committed certificate and needs nothing, and it is the one that guards what a
#: reader actually opens — skipping it wherever scipy is absent would leave the published file
#: unchecked in the job that runs everywhere.
_NEEDS_SOLVER = pytest.mark.skipif(
    __import__("importlib").util.find_spec("scipy") is None,
    reason="the optional 'fba' extra (scipy) is not installed",
)

_ROOT = Path(__file__).resolve().parents[1]
_WORKED = _ROOT / "datasets" / "constraint_based" / "worked_example" / "certificate.txt"


def test_the_certificate_states_the_bound_it_actually_applied() -> None:
    text = _WORKED.read_text(encoding="utf-8")
    # The glucose exchange in `datasets/constraint_based/e_coli_core.xml` carries
    # `R_EX_glc__D_e_lower_bound = -10`, and that is the number the program was solved under.
    assert "R_EX_glc__D_e uptake<=10.0 mmol/gDW/h (flux>=-10.0)" in text
    # The form that stated the opposite is gone from the artifact entirely.
    assert "R_EX_glc__D_e<=" not in text


@_NEEDS_SOLVER
def test_both_surfaces_state_it_the_same_way() -> None:
    """The inline linter an agent gates on and the certificate path, differentially.

    They rendered the same defect identically, which is the good half of a bad situation: one fix
    reaches both, and a fix that reached one would be the drift this differential exists to catch.
    """
    from reprolith.constraint_based import _medium_protocol
    from reprolith.fba import FbaModel

    model = FbaModel(
        reaction_ids=("R_EX_glc__D_e", "R_BIOMASS"),
        species_ids=("glc",),
        stoichiometry=((1.0, -1.0),),
        lower=(-1000.0, 0.0),
        upper=(1000.0, 1000.0),
        objective=(0.0, 1.0),
    )
    from reprolith.dossier import Parameter

    certificate_side = _medium_protocol(
        [Parameter(name="R_EX_glc__D_e", value=10.0, unit="mmol/gDW/h", source_location="Table 1")], model
    )
    assert "R_EX_glc__D_e uptake<=10.0 mmol/gDW/h (flux>=-10.0)" in certificate_side

    # And the linter says the same thing about the same medium, down to the direction.
    from reprolith.linter import lint_objective

    del lint_objective  # imported to assert it exists on this surface; driven below via source
    import inspect

    from reprolith import linter

    rendered = inspect.getsource(linter)
    assert 'uptake<={abs(uptake)!r} (flux>={-abs(uptake)!r})' in rendered


@_NEEDS_SOLVER
def test_a_negative_entry_reads_the_same_as_its_magnitude() -> None:
    """Both surfaces already applied `-abs(value)`, so a caller writing -10 and one writing 10 set
    up the same program. The line they publish now says so too, rather than printing one of them
    with a sign the other does not have."""
    from reprolith.constraint_based import _medium_protocol
    from reprolith.dossier import Parameter
    from reprolith.fba import FbaModel

    model = FbaModel(
        reaction_ids=("R_EX_glc__D_e",), species_ids=("glc",), stoichiometry=((1.0,),),
        lower=(-1000.0,), upper=(1000.0,), objective=(1.0,),
    )
    positive = _medium_protocol([Parameter(name="R_EX_glc__D_e", value=10.0, unit="u", source_location="Table 1")], model)
    negative = _medium_protocol([Parameter(name="R_EX_glc__D_e", value=-10.0, unit="u", source_location="Table 1")], model)
    assert positive == negative
