"""A reported reaction flux can be certified, and where it cannot the abstention says why.

`judge_flux` has been in this class since it was written, with its alternate-optima honesty worked
out — a flux the interval pins is reproduced, one merely *inside* a wide interval is abstained on
because the model does not determine it, and one outside fails. The spec has named a reported flux
as a reproduction target for just as long. No front end could reach it: `certify_constraint_based`
judged objective values, and then essential sets, and nothing else.

The interesting case is the abstention. "The model does not determine this flux" is the same
sentence whether the freedom is real biology or a stoichiometric cycle carrying no driving force —
and on *E. coli* core it is the second: the only two reactions whose interval is not pinned at the
optimum are `FRD7` and `SUCDi`, the textbook infeasible loop. So the reason says which.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the optional 'fba' extra (scipy) is not installed")

from reprolith import PaperIdentity, ingest_fbc_sbml  # noqa: E402
from reprolith.constraint_based import (  # noqa: E402
    FluxClaim,
    FluxRangeClaim,
    certify_constraint_based,
)
from reprolith.enums import OverallVerdict, Verdict  # noqa: E402
from reprolith.fba import flux_variability, solver_pin  # noqa: E402
from reprolith.persistence import dossier_from_dict  # noqa: E402

_CB = Path(__file__).parent.parent / "datasets" / "constraint_based"
_FVA = json.loads(
    (_CB / "cross_validation" / "e_coli_core_fva.json").read_text(encoding="utf-8")
)["intervals"]


def _certificate(*claims: FluxClaim):
    return certify_constraint_based(
        dossier_from_dict(
            json.loads((_CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
        ),
        sbml=(_CB / "e_coli_core.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core"),
        engine_pin=solver_pin(),
        fluxes=list(claims),
    )


def _claim(**kw) -> FluxClaim:
    base = dict(
        claim_id="aconitase", quantity="aconitase flux at maximal growth",
        reaction_id="R_ACONTa", reported=_FVA["ACONTa"][0],
        source_location="COBRApy flux variability of this model file",
    )
    base.update(kw)
    return FluxClaim(**base)


# --- a pinned flux is a reproduction --------------------------------------------------------------


def test_a_flux_the_interval_pins_reproduces() -> None:
    certificate = _certificate(_claim())
    assessment = certificate.assessments[-1]
    assert assessment.verdict is Verdict.REPRODUCED
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert "flux variability of R_ACONTa at the optimum: [6.00725, 6.00725]" in assessment.protocol


def test_a_flux_outside_the_feasible_interval_fails() -> None:
    certificate = _certificate(_claim(reported=_FVA["ACONTa"][0] * 2))
    assert certificate.assessments[-1].verdict is Verdict.FAILED


# --- the abstention, and what it now says ---------------------------------------------------------


def test_a_flux_the_model_leaves_free_abstains_and_names_the_loop() -> None:
    # SUCDi's interval runs from 5.06 to 1000 at the optimum, and it does so because SUCDi and FRD7
    # form an internal cycle with no thermodynamic driving force. Certifying a reported value
    # anywhere in that range would claim the model produces it; the model merely permits it.
    certificate = _certificate(_claim(
        claim_id="succinate-dehydrogenase", reaction_id="R_SUCDi", reported=5.064375661,
    ))
    assessment = certificate.assessments[-1]
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "The loop law does pin it" in assessment.root_cause
    # The certificate-level verdict is derived from the claims that *were* judged, so an
    # abstention beside a reproduction does not downgrade it — the shared rule, and the same one
    # that makes a certificate with nothing evaluable `blocked` rather than `not-reproduced`. What
    # a reader is owed is that the abstention is visible, and it is: on the claim line, in the
    # per-verdict counts, and in the gap report.
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert sum(1 for a in certificate.assessments if a.verdict is Verdict.NOT_EVALUABLE) == 1


def test_the_same_flux_certifies_when_the_claim_states_loopless_analysis() -> None:
    # The analysis is the claim's, not this engine's preference: a source that removed infeasible
    # loops is judged against the interval that analysis produces, and there SUCDi is pinned.
    certificate = _certificate(_claim(
        claim_id="succinate-dehydrogenase", reaction_id="R_SUCDi", reported=5.064375661,
        loopless=True,
    ))
    assessment = certificate.assessments[-1]
    assert assessment.verdict is Verdict.REPRODUCED
    assert "loopless flux variability of R_SUCDi" in assessment.protocol


# --- what it refuses -------------------------------------------------------------------------------


def test_a_claim_naming_a_reaction_the_model_does_not_have_is_refused() -> None:
    with pytest.raises(ValueError, match="which this model does not have"):
        _certificate(_claim(reaction_id="R_NOT_A_REACTION"))


# --- the subset the interval is computed over ------------------------------------------------------


def test_flux_variability_computes_only_the_reactions_asked_for() -> None:
    # Two more linear programs per reaction: judging one reported flux on a genome-scale model
    # should not solve every column. The subset must give the same interval as the full sweep.
    model = ingest_fbc_sbml((_CB / "e_coli_core.xml").read_text(encoding="utf-8"))
    index = model.reaction_index("R_ACONTa")
    subset = flux_variability(
        model.stoichiometry, model.objective, model.lower, model.upper, reactions=[index]
    )
    assert len(subset) == 1
    full = flux_variability(model.stoichiometry, model.objective, model.lower, model.upper)
    assert subset[0] == pytest.approx(full[index])


# --- the range itself, which is a different claim from a value inside it --------------------------


def _range_certificate(**kw):
    base = dict(
        claim_id="succinate-range", quantity="SUCDi flux range at maximal growth",
        reaction_id="R_SUCDi", reported_min=_FVA["SUCDi"][0], reported_max=_FVA["SUCDi"][1],
        source_location="COBRApy flux variability of this model file",
    )
    base.update(kw)
    return certify_constraint_based(
        dossier_from_dict(
            json.loads((_CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
        ),
        sbml=(_CB / "e_coli_core.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core"),
        engine_pin=solver_pin(),
        flux_ranges=[FluxRangeClaim(**base)],
    )


def test_a_reported_range_reproduces_where_a_value_inside_it_would_abstain() -> None:
    # The same reaction, the same run, and the opposite verdict — because the two claims say
    # different things. "SUCDi carries 5.06" is not determined by this model; "SUCDi can carry
    # 5.06 to 1000" is exactly what the model says.
    assessment = _range_certificate().assessments[-1]
    assert assessment.verdict is Verdict.REPRODUCED
    assert "worst-matched bound" in assessment.discrepancy


def test_the_worse_matched_bound_governs_rather_than_the_average() -> None:
    # A range whose lower bound is right and whose upper bound is out by 40% is not a
    # 20%-disagreeing range. Averaging the two would publish this as a partial match.
    certificate = _range_certificate(reported_max=_FVA["SUCDi"][1] * 0.6)
    assessment = certificate.assessments[-1]
    assert assessment.verdict is Verdict.FAILED
    assert "the upper one" in assessment.discrepancy


def test_a_zero_bound_is_judged_against_the_range_s_own_width() -> None:
    # FRD7 runs from 0 to 994.9 here. A relative error against a reported zero has no magnitude to
    # normalize by, and an absolute one would make the verdict depend on the flux unit — so the
    # scale is the range the claim itself states.
    certificate = _range_certificate(
        claim_id="frd7-range", reaction_id="R_FRD7",
        reported_min=_FVA["FRD7"][0], reported_max=_FVA["FRD7"][1],
    )
    assert certificate.assessments[-1].verdict is Verdict.REPRODUCED


def test_a_range_reported_upside_down_is_refused() -> None:
    with pytest.raises(ValueError, match="not a pair of numbers in an arbitrary order"):
        _range_certificate(reported_min=10.0, reported_max=1.0)
