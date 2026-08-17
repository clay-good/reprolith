"""Population / inter-individual variability reproduction (roadmap #7).

The oracle judges a population figure — a percentile envelope over time — band-for-band,
governed by the worst-matched band, and qualifies the verdict because reproduction depends on
the reconstructed variability model and the sampling (spec: simulation-oracle — "Distributional
(population) claims are compared honestly").
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from reprolith import (
    Attribution,
    EnginePin,
    FailureMode,
    Fault,
    OverallVerdict,
    PaperIdentity,
    PercentileBand,
    ReferenceKind,
    Tolerance,
    ToleranceSource,
    Verdict,
    band_envelope_distance,
    build_certificate,
    judge_distribution,
)

# A three-band envelope: lower percentile, median, upper percentile over five time points.
_REF = (
    PercentileBand(5.0, (0.4, 0.9, 1.6, 1.0, 0.5)),
    PercentileBand(50.0, (1.0, 2.0, 3.6, 2.2, 1.1)),
    PercentileBand(95.0, (1.8, 3.4, 6.0, 3.8, 1.9)),
)

_SHORTFALL = Attribution(
    mode=FailureMode.UNSPECIFIED_VARIABILITY_MODEL,
    implicated="between-subject variability on clearance (dossier omits ω²_CL)",
    fault=Fault.MANUSCRIPT,
)


def _perturb(envelope: tuple[PercentileBand, ...], factor: float) -> tuple[PercentileBand, ...]:
    return tuple(
        PercentileBand(b.percentile, tuple(v * factor for v in b.curve)) for b in envelope
    )


# --- percentile-band envelope comparison -------------------------------------------


def test_matching_envelope_reproduces_but_is_qualified() -> None:
    predicted = _perturb(_REF, 1.02)  # 2% high everywhere, inside the numeric band default
    a = judge_distribution(
        claim_id="c", quantity="concentration percentile envelope",
        source_location="Fig 5", reference=_REF, predicted=predicted,
    )
    assert a.verdict is Verdict.REPRODUCED
    assert a.method == "distribution-band-distance"
    assert a.assumption_qualified is True  # population reproduction is qualified by default


def test_worst_band_governs_the_verdict() -> None:
    # Median matches perfectly, but the upper tail is blown out — the envelope must fail on the
    # weakest band rather than pass on the good median.
    predicted = (
        _REF[0],
        _REF[1],
        PercentileBand(95.0, (3.6, 6.8, 12.0, 7.6, 3.8)),  # 2x the reference upper band
    )
    a = judge_distribution(
        claim_id="c", quantity="concentration percentile envelope",
        source_location="Fig 5", reference=_REF, predicted=predicted,
        attribution=_SHORTFALL,
    )
    assert a.verdict is Verdict.FAILED
    assert "P95" in a.discrepancy  # the discrepancy names the governing percentile
    assert a.root_cause == "unspecified-between-subject-variability-model"


def test_worst_band_helper_returns_governing_percentile() -> None:
    predicted = (
        _REF[0],
        _REF[1],
        PercentileBand(95.0, (3.6, 6.8, 12.0, 7.6, 3.8)),
    )
    distance, band = band_envelope_distance(_REF, predicted)
    assert band.percentile == 95.0
    assert distance > 0.0


def test_figure_reference_widens_the_distributional_tolerance() -> None:
    predicted = _perturb(_REF, 1.20)  # 20% high: partial vs numeric (15/35), reproduced vs figure
    numeric = judge_distribution(
        claim_id="c", quantity="envelope", source_location="Fig 5",
        reference=_REF, predicted=predicted, attribution=_SHORTFALL,
    )
    figure = judge_distribution(
        claim_id="c", quantity="envelope", source_location="Fig 5",
        reference=_REF, predicted=predicted, reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    assert numeric.verdict is Verdict.PARTIAL
    assert figure.verdict is Verdict.REPRODUCED


def test_qualification_can_be_lifted_when_variability_is_fully_specified() -> None:
    a = judge_distribution(
        claim_id="c", quantity="envelope", source_location="Fig 5",
        reference=_REF, predicted=_perturb(_REF, 1.01), assumption_qualified=False,
    )
    assert a.verdict is Verdict.REPRODUCED
    assert a.assumption_qualified is False


def test_non_pass_without_attribution_is_rejected() -> None:
    with pytest.raises(ValueError):
        judge_distribution(
            claim_id="c", quantity="envelope", source_location="Fig 5",
            reference=_REF, predicted=_perturb(_REF, 2.0),  # fails, but no attribution
        )


def test_override_tolerance_provenance_is_recorded() -> None:
    tol = Tolerance(
        0.05, 0.10, ToleranceSource.PAPER_STATED, rationale="paper reports a 5% prediction band"
    )
    a = judge_distribution(
        claim_id="c", quantity="envelope", source_location="Fig 5",
        reference=_REF, predicted=_perturb(_REF, 1.02), tolerance=tol,
    )
    assert a.tolerance_source == "paper-stated"


# --- envelope validation -----------------------------------------------------------


def test_mismatched_percentiles_are_rejected() -> None:
    other = (
        PercentileBand(10.0, (0.4, 0.9, 1.6, 1.0, 0.5)),
        PercentileBand(50.0, (1.0, 2.0, 3.6, 2.2, 1.1)),
        PercentileBand(90.0, (1.8, 3.4, 6.0, 3.8, 1.9)),
    )
    with pytest.raises(ValueError, match="same percentiles"):
        band_envelope_distance(_REF, other)


def test_mismatched_band_length_is_rejected() -> None:
    predicted = (
        PercentileBand(5.0, (0.4, 0.9)),  # too few points
        _REF[1],
        _REF[2],
    )
    with pytest.raises(ValueError, match="same points"):
        band_envelope_distance(_REF, predicted)


def test_percentile_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        PercentileBand(0.0, (1.0,))
    with pytest.raises(ValueError):
        PercentileBand(100.0, (1.0,))


def test_duplicate_percentile_in_envelope_is_rejected() -> None:
    dup = (PercentileBand(50.0, (1.0, 2.0)), PercentileBand(50.0, (1.0, 2.1)))
    with pytest.raises(ValueError, match="distinct"):
        band_envelope_distance(dup, dup)


# --- determinism and certificate integration ---------------------------------------


def test_repeated_evaluation_is_identical() -> None:
    def run():
        return judge_distribution(
            claim_id="c", quantity="envelope", source_location="Fig 5",
            reference=_REF, predicted=_perturb(_REF, 1.03),
        )

    assert run() == run()


def test_certify_population_assembles_a_qualified_certificate() -> None:
    from reprolith import OverallVerdict, PopulationClaim, certify_population

    cert = certify_population(
        paper=PaperIdentity(doi="10.0/pop2", title="A population PK model"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        claims=[
            PopulationClaim(
                claim_id="env", quantity="concentration envelope",
                reported=_REF, predicted=_perturb(_REF, 1.02), source_location="Fig 5",
                protocol="virtual population: 1000 subjects, seed 7",
            ),
        ],
    )
    assert cert.assessments[0].verdict is Verdict.REPRODUCED
    assert cert.assessments[0].assumption_qualified is True
    # A reproduced-but-qualified population figure cannot earn a clean overall verdict.
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    # And the qualification names what it is qualifying: the sampling behind the bands, on the
    # record as a load-bearing assumption rather than a flag pointing at nothing.
    assumption = cert.assumptions[0]
    assert assumption.id == "population-sampling-env"
    assert assumption.chosen == "virtual population: 1000 subjects, seed 7"
    assert assumption.load_bearing is True


def test_qualified_population_reproduction_yields_partial_certificate() -> None:
    # A population figure that reproduces still cannot earn a clean overall verdict: the
    # qualification forbids an unqualified full reproduction (done-when: "a qualified verdict").
    a = replace(
        judge_distribution(
            claim_id="c", quantity="concentration percentile envelope",
            source_location="Fig 5", reference=_REF, predicted=_perturb(_REF, 1.02),
        ),
        # The builder refuses a distributional verdict that does not say what produced the bands,
        # whichever route assembled it — see test_a_population_verdict_records_the_ensemble_it_rests_on.
        protocol="virtual population: 250 subjects, seed 3",
    )
    cert = build_certificate(
        paper=PaperIdentity(doi="10.0/pop", title="A population PK model"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        assessments=[a],
    )
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED


def test_lint_distribution_inline_verdict() -> None:
    from reprolith import lint_distribution

    reported = [{"percentile": b.percentile, "curve": list(b.curve)} for b in _REF]
    good_pred = [{"percentile": b.percentile, "curve": [v * 1.02 for v in b.curve]} for b in _REF]
    result = lint_distribution(reported, good_pred)
    assert result.verdict is Verdict.REPRODUCED
    assert result.method == "distribution-band-distance"
    assert result.scope.machine

    blown = [{"percentile": b.percentile, "curve": [v * (2.0 if b.percentile == 95.0 else 1.0)
                                                    for v in b.curve]} for b in _REF]
    assert lint_distribution(reported, blown).verdict is Verdict.FAILED


def test_lint_abstains_rather_than_judging_a_diverged_run() -> None:
    """A non-finite run has no comparable value; the linter must abstain like the oracle does."""
    from reprolith import Verdict, lint_distribution

    nan = float("nan")
    reported = [{"percentile": 50, "curve": [1.0, 2.0, 3.0]}]
    predicted = [{"percentile": 50, "curve": [nan, nan, nan]}]
    assert lint_distribution(reported, predicted).verdict is Verdict.NOT_EVALUABLE


def test_a_population_verdict_records_the_ensemble_it_rests_on() -> None:
    """An envelope's verdict moves with its sample size, so the sampling must travel with it."""
    from reprolith import EnginePin, PaperIdentity, PopulationClaim, certify_population

    claim = PopulationClaim(
        claim_id="p1", quantity="plasma concentration envelope",
        reported=_REF, predicted=_REF, source_location="Fig 3",
        protocol="virtual population: 500 subjects, seed 20260816",
    )
    cert = certify_population(
        paper=PaperIdentity(title="P", doi="10.1/x"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        claims=[claim],
    )
    assert cert.assessments[0].protocol == "virtual population: 500 subjects, seed 20260816"
    assert cert.assessments[0].to_dict()["protocol"] == claim.protocol

    # Omitting it is refused where the claim is built. Reprolith does not simulate the population
    # here — the bands are handed in — so the sampling is the only evidence on the certificate that
    # a run produced them, and `predicted == reported` would otherwise publish a reproduction of a
    # population nobody can re-draw.
    with pytest.raises(ValueError, match="states no protocol"):
        PopulationClaim(claim_id="p1", quantity="q", reported=_REF, predicted=_REF,
                        source_location="Fig 3", protocol="  ")
