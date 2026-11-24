"""The sampling choice can stop being one, and the rule that says when (spec: stochastic-class).

A sampled estimate is normally qualified: a certificate reading `reproduced` off four hundred
trajectories is reading off *one* draw, and another seed would move it. But that is a statement
about a size, and a size can be bought — which is what every stochastic protocol line in this
repository has been telling its reader to buy. These check that buying it works, and that the rule
which spends it is keyed on the band the claim is judged in rather than on how close the claim
happened to land.
"""

from __future__ import annotations

import importlib.util
import math

import pytest
from reprolith import Verdict
from reprolith.model import PaperIdentity
from reprolith.oracle import (
    SAMPLING_MARGIN_BUDGET,
    ComparisonMethod,
    ReferenceKind,
    default_tolerance,
    sample_to_settle,
    sampling_is_decisive,
)
from reprolith.stochastic import (
    Reaction,
    StochasticClaim,
    certify_stochastic,
    solver_pin,
)

_TOLERANCE = default_tolerance(ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC)
#: A pure immigration-death process: Poisson stationary mean k/γ, closed-form and exact.
_IMMIGRATION_DEATH = [Reaction(10.0, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())]
_PIN = solver_pin()


def test_the_rule_is_keyed_on_the_band_and_not_on_the_residual() -> None:
    """The trap the spatial class fell into first, refused by construction here.

    A residual is partly made of the very sampling noise this is measuring, so a bar compared
    against the distance from an answer to its verdict line clears *because* the draw was lucky.
    This takes no residual at all, which is what makes that impossible rather than unlikely.
    """
    tenth = SAMPLING_MARGIN_BUDGET * _TOLERANCE.reproduced_within
    assert sampling_is_decisive(relative_error_bar=tenth, tolerance=_TOLERANCE)
    assert not sampling_is_decisive(relative_error_bar=tenth * 1.01, tolerance=_TOLERANCE)
    # The signature is the argument: there is nowhere to put a residual.
    with pytest.raises(TypeError):
        sampling_is_decisive(  # type: ignore[call-arg]
            relative_error_bar=tenth, tolerance=_TOLERANCE, relative_error=0.0
        )


def test_the_count_the_certificate_advertises_always_buys_the_discharge() -> None:
    """The invariant that lets the protocol line publish one count instead of two.

    A certificate tells its reader how many trajectories would put the sampling error a tenth of
    the way to the nearest verdict line. The rule that *discharges* the qualification asks for a
    tenth of the whole band instead — a different number, and a reader who bought the advertised
    one and found the assumption still standing would have been sold one thing and given another.
    It cannot happen in that direction: for a claim inside its band the margin is at most the band,
    so the advertised count is the larger of the two. Checked across the shape of claim this class
    publishes rather than asserted from the algebra.
    """
    size, bar = 400, 0.02
    for residual in (0.0, 0.001, 0.01, 0.02, 0.049):
        settle = sample_to_settle(
            relative_error=residual, relative_error_bar=bar, size=size, tolerance=_TOLERANCE
        )
        assert settle is not None, residual
        advertised, _margin = settle
        # The bar falls as 1/sqrt(n): this is what buying the advertised count leaves it at.
        bought = bar / math.sqrt(advertised / size)
        assert sampling_is_decisive(relative_error_bar=bought, tolerance=_TOLERANCE), residual


def test_an_ensemble_large_enough_drops_the_qualification_and_a_smaller_one_keeps_it() -> None:
    """The end-to-end consequence, and its mutation: the same claim, two ensemble sizes.

    The reference is the closed-form Poisson mean, so what changes between the two runs is the
    draw and nothing else. At four hundred trajectories the ensemble's own bar is a third of the
    pass band and the certificate is qualified for it; at four thousand the bar is a tenth, and
    both the assumption and the `partially-reproduced` go.
    """
    def certify(trajectories: int):
        return certify_stochastic(
            paper=PaperIdentity(title="Immigration-death", doi=""),
            engine_pin=_PIN,
            n_species=1, reactions=_IMMIGRATION_DEATH, initial=[0],
            claims=[StochasticClaim(
                claim_id="mean", quantity="mean copy number", species=0,
                reported_mean=10.0, source_location="closed-form",
                duration=40.0, trajectories=trajectories, seed=20260807,
            )],
        )

    small = certify(400)
    (assessment,) = small.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    assert assessment.assumption_qualified is True
    assert small.assumptions and small.assumptions[0].id == "ssa-sampling-mean"
    assert "would put the sampling error" in assessment.protocol

    large = certify(4000)
    (assessment,) = large.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    assert assessment.assumption_qualified is False
    assert large.assumptions == ()
    # And the protocol line says why this one carries no assumption where its sibling does.
    assert "not a choice the verdict rests on" in assessment.protocol


def test_the_discharge_is_not_a_way_to_pass() -> None:
    """A draw can stop being a choice and the claim still be wrong — the two are separate.

    Worth pinning because the rule removes a qualification, and a rule that removed one from a
    *failing* claim would read as the engine excusing itself. The reference here is wrong by half,
    far outside anything an ensemble's bar explains.
    """
    certificate = certify_stochastic(
        paper=PaperIdentity(title="Immigration-death", doi=""),
        engine_pin=_PIN,
        n_species=1, reactions=_IMMIGRATION_DEATH, initial=[0],
        claims=[StochasticClaim(
            claim_id="mean", quantity="mean copy number", species=0,
            reported_mean=5.0, source_location="closed-form",
            duration=40.0, trajectories=4000, seed=20260807,
        )],
    )
    (assessment,) = certificate.assessments
    assert assessment.verdict is Verdict.FAILED


@pytest.mark.skipif(
    importlib.util.find_spec("libsbml") is None,
    reason="writing the network as SBML needs the optional 'engine' extra (python-libsbml)",
)
def test_the_inline_linter_says_what_the_certificate_says() -> None:
    """The surface-parity invariant this class already holds for its abstention rule.

    Whether a draw is a choice the verdict rests on is a property of the ensemble, not of which
    surface asked — and the linter's caller is an agent that acts on the answer immediately, where
    the certificate's reader is a person who can go and look. A discharge sentence the certificate
    printed and the linter did not would be the seam the shared cost clause exists to close.
    """
    from reprolith.linter import lint_stochastic
    from reprolith.sbml import build_stochastic_sbml

    sbml = build_stochastic_sbml(
        ["S0"], _IMMIGRATION_DEATH, [0], model_id="immigration_death"
    )
    decided = lint_stochastic(
        sbml, species=0, reported_mean=10.0, duration=40.0, trajectories=4000, seed=20260807
    )
    undecided = lint_stochastic(
        sbml, species=0, reported_mean=10.0, duration=40.0, trajectories=400, seed=20260807
    )
    assert "not a choice the verdict rests on" in decided.protocol
    assert "not a choice the verdict rests on" not in undecided.protocol
