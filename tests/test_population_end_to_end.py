"""A population figure walked from the model to the certificate, with nothing hand-written.

`simulate_population` produces an envelope and `certify_population` judges one, and until now
nothing joined them: every test of the simulator stopped at its bands, and every test of the
certifier started from bands somebody typed. The two halves of roadmap #7 met only in a docstring.

The join is also where an envelope's *grid* has to line up. A paper's reported bands are read at
the times the paper shows; the simulated ones come off the run's own sample points, and a band
comparison of two different grids is not a comparison. That was already refused — but from two
frames down inside `worst_point_deviation`, as a bare length assertion naming neither the band nor
either count, which is what a walk from a model to a certificate is likely to meet.

The reference is the closed form the simulator is already validated against — a one-compartment IV
bolus with a log-normal volume, whose percentiles are `(D/V)·exp(-k·t)·exp(omega·z_p)` exactly.
Standing in for a paper's published envelope, it is mathematics rather than a picture, the same
fence roadmap #7 carries: no paper's population figure is in this corpus.

Needs the `engine` extra.
"""

from __future__ import annotations

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import (  # noqa: E402
    OverallVerdict,
    PaperIdentity,
    PercentileBand,
    PopulationClaim,
    RunMetadata,
    SubjectVariability,
    Verdict,
    certify_population,
    engine_pin,
    render_human,
    simulate_population,
)
from test_population_simulation import _MODEL, _closed_form  # noqa: E402

_CV = 0.3
_SUBJECTS = 500
_SEED = 20260901
_PERCENTILES = (5.0, 50.0, 95.0)


def _paper_envelope(times: tuple[float, ...], omega: float) -> tuple[PercentileBand, ...]:
    """The envelope a paper would print if its population were exactly the one modelled."""
    return tuple(
        PercentileBand(
            percentile=pct,
            curve=tuple(_closed_form(pct, omega, t) for t in times),
        )
        for pct in _PERCENTILES
    )


def _walk(model: str = _MODEL, *, subjects: int = _SUBJECTS):
    """Model -> ensemble -> bands -> certificate. Nothing between them is typed by hand."""
    spec = SubjectVariability(parameter="V", cv=_CV)
    run = simulate_population(
        model, "C", duration=12.0, steps=12,
        variability=(spec,), subjects=subjects, seed=_SEED, percentiles=_PERCENTILES,
    )
    claim = PopulationClaim(
        claim_id="fig2-envelope",
        quantity="C 5th/50th/95th percentile envelope",
        reported=_paper_envelope(run.times, spec.omega()),
        predicted=run.bands,
        source_location="Figure 2, the shaded band",
        protocol=run.protocol,
    )
    return run, certify_population(
        paper=PaperIdentity(title="A synthetic population, with a synthetic envelope", doi=""),
        engine_pin=engine_pin(),
        claims=[claim],
    )


def test_a_population_figure_walks_from_a_model_to_a_verdict() -> None:
    """The walk that did not exist. Both halves were built and tested; neither had met the other."""
    run, certificate = _walk()
    assessment, = certificate.assessments

    assert assessment.verdict is Verdict.REPRODUCED
    # And the certificate as a whole is *not* an unqualified reproduction: a population verdict
    # rests on a reconstructed variability model and a sampling choice, so it is qualified by
    # construction. The class's honesty invariant, exercised end to end for the first time.
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert assessment.assumption_qualified

    # The sampling reaches the certificate from the run that produced it, rather than from a
    # string the caller wrote: an envelope's verdict moves with its subject count and seed, and
    # this is the only evidence on the certificate of which ones were in force.
    assert assessment.protocol == run.protocol
    assert f"{_SUBJECTS} subjects" in assessment.protocol and f"seed {_SEED}" in assessment.protocol
    assert "V (CV 0.3)" in assessment.protocol

    rendered = render_human(
        certificate, RunMetadata(created_at="t", actor="a", tool_version="0.0.1")
    )
    assert "tol=reproduced<=0.15, partial<=0.35" in rendered  # the distributional band
    assert f"seed {_SEED}" in rendered
    # The qualification is written down as an assumption naming the sampling, not left as a flag.
    assert "population-sampling-fig2-envelope" in rendered


def test_the_certificate_is_not_vacuous_on_a_population_the_figure_contradicts() -> None:
    """The same envelope against a model eliminating half as fast: not a pass, and root-caused.

    Worth walking rather than asserting, because the failure has to survive the *whole* path — the
    ensemble runs fine, every band is finite, and the only thing wrong is that the population is
    the wrong one.
    """
    slower = _MODEL.replace('id="k" value="0.2"', 'id="k" value="0.1"')
    _, certificate = _walk(slower)
    assessment, = certificate.assessments

    assert assessment.verdict is not Verdict.REPRODUCED
    assert assessment.root_cause and assessment.fault_hypothesis


def test_the_ensemble_size_reaches_the_verdict_and_not_only_the_protocol() -> None:
    """What the sampling-cost measurement predicts, walked end to end.

    At 500 subjects a flawless reproduction of the right population clears the 15% budget; the
    same walk at the smallest ensemble the simulator will run is close enough to the budget that
    the subject count is visibly a term in the verdict rather than a footnote to it. Both are the
    *same* model against the *same* reference: only the ensemble changed.
    """
    big, _ = _walk()
    small, _ = _walk(subjects=30)

    def worst(run) -> float:
        return max(
            abs(b.curve[i] - _closed_form(b.percentile, SubjectVariability("V", _CV).omega(), t))
            / _closed_form(b.percentile, SubjectVariability("V", _CV).omega(), t)
            for b in run.bands
            for i, t in enumerate(run.times)
        )

    assert worst(big) < worst(small)
    assert worst(big) < 0.10


def test_two_envelopes_on_different_grids_are_refused_by_name() -> None:
    """Refused before, but not in words the caller could act on.

    The mismatch was always caught (`tests/test_population.py` has held that since the band
    statistics were written). What it was caught *by* was a bare length assertion two frames down
    inside `worst_point_deviation` — "reference and predicted must be sampled at the same points" —
    naming no percentile, no counts, and no envelope. `_paired_bands` is the function that promises
    to refuse "anything the comparison cannot align", and this was the one alignment it did not
    check. Pinned from the end of the walk that meets it, because a caller who has just simulated a
    population against a paper's printed times is who reads that message.
    """
    spec = SubjectVariability(parameter="V", cv=_CV)
    run = simulate_population(
        _MODEL, "C", duration=12.0, steps=12,
        variability=(spec,), subjects=_SUBJECTS, seed=_SEED, percentiles=_PERCENTILES,
    )
    coarser = tuple(12.0 * i / 6 for i in range(7))  # the paper printed seven times, not thirteen
    claim = PopulationClaim(
        claim_id="fig2-envelope",
        quantity="C 5th/50th/95th percentile envelope",
        reported=_paper_envelope(coarser, spec.omega()),
        predicted=run.bands,
        source_location="Figure 2, the shaded band",
        protocol=run.protocol,
    )
    with pytest.raises(ValueError, match=r"5th percentile band is reported over 7 sample\(s\) and "
                                          r"predicted over 13"):
        certify_population(
            paper=PaperIdentity(title="t", doi=""), engine_pin=engine_pin(), claims=[claim],
        )
