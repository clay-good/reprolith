"""Simulating a virtual population, checked against a distribution known in closed form.

`certify_population` and `judge_distribution` took the simulated bands as given; producing them was
the deferred half of roadmap #7. This is that half, and it is validated the way the spatial and
stochastic classes are — against mathematics, not against itself.

The model is a one-compartment IV bolus, `C(t) = (D/V)·exp(-k·t)`, with the volume varying
log-normally between subjects. Then `ln C(t)` is normal with mean `ln(D/V) - k·t` and standard
deviation `omega`, so every percentile band has a closed form: `(D/V)·exp(-k·t)·exp(omega·z_p)`.
A simulator that gets the variability model, the draws, or the percentile definition wrong misses
it, and the miss is in a direction the test can name.

Needs the `engine` extra.
"""

from __future__ import annotations

import math
from statistics import NormalDist

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import (  # noqa: E402
    OverallVerdict,
    PaperIdentity,
    PercentileBand,
    PopulationClaim,
    SubjectVariability,
    certify_population,
    engine_pin,
    simulate_population,
)

_D, _V, _K = 100.0, 10.0, 0.2

_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="one_compartment">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="D" value="100" constant="true"/>
      <parameter id="V" value="10" constant="true"/>
      <parameter id="k" value="0.2" constant="true"/>
      <parameter id="Vd" value="10" constant="false"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><divide/><ci>D</ci><ci>V</ci></apply>
        </math>
      </initialAssignment>
    </listOfInitialAssignments>
    <listOfRules>
      <assignmentRule variable="Vd">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>V</ci></math>
      </assignmentRule>
      <rateRule variable="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>C</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""


def _closed_form(percentile: float, omega: float, time: float) -> float:
    """The exact percentile of C(t) when V is log-normal: median times exp(omega·z_p)."""
    return (_D / _V) * math.exp(-_K * time) * math.exp(omega * NormalDist().inv_cdf(percentile / 100))


def test_the_envelope_matches_the_distribution_it_should_have() -> None:
    """500 subjects at 30% CV. The sampling error of an empirical P5 at that size is about 3% of
    the value, so a 10% band is a real check and not a formality — a mean-preserving variability
    model (the other common convention) shifts every band by 4.4% and a nearest-rank percentile
    puts P5 two order statistics away."""
    spec = SubjectVariability(parameter="V", cv=0.3)
    run = simulate_population(
        _MODEL, "C", duration=12.0, steps=12,
        variability=(spec,), subjects=500, seed=20260827,
    )
    assert [band.percentile for band in run.bands] == [5.0, 50.0, 95.0]
    for band in run.bands:
        for index, time in enumerate(run.times):
            expected = _closed_form(band.percentile, spec.omega(), time)
            assert band.curve[index] == pytest.approx(expected, rel=0.10), (
                f"{band.label()} at t={time}"
            )


def test_the_median_band_is_the_model_itself() -> None:
    """Median-preserving is the whole point of the convention: the P50 of the population is the
    trajectory the model's own parameter values produce, not one shifted by exp(omega²/2)."""
    run = simulate_population(
        _MODEL, "C", duration=12.0, steps=12,
        variability=(SubjectVariability(parameter="V", cv=0.5),), subjects=500, seed=7,
    )
    median = next(band for band in run.bands if band.percentile == 50.0)
    for index, time in enumerate(run.times):
        assert median.curve[index] == pytest.approx((_D / _V) * math.exp(-_K * time), rel=0.06)


def test_the_same_seed_gives_the_same_population() -> None:
    """A band a rerun cannot reproduce is not evidence. The draws go through an explicit inverse
    CDF over seeded uniforms, so this holds across interpreter versions too."""
    kwargs = dict(
        duration=6.0, steps=6, variability=(SubjectVariability(parameter="V", cv=0.3),),
        subjects=40,
    )
    first = simulate_population(_MODEL, "C", seed=11, **kwargs)  # type: ignore[arg-type]
    again = simulate_population(_MODEL, "C", seed=11, **kwargs)  # type: ignore[arg-type]
    other = simulate_population(_MODEL, "C", seed=12, **kwargs)  # type: ignore[arg-type]
    assert first.bands == again.bands
    assert first.protocol == again.protocol
    assert first.bands != other.bands


def test_the_protocol_names_everything_the_bands_depend_on() -> None:
    run = simulate_population(
        _MODEL, "C", duration=6.0, steps=6,
        variability=(SubjectVariability(parameter="V", cv=0.3),), subjects=40, seed=11,
    )
    for expected in ("40 subjects", "seed 11", "V (CV 0.3)", "median-preserving",
                     "linearly interpolated", "duration=6.0", "steps=6", "read=[C]"):
        assert expected in run.protocol
    # An envelope of forty subjects and one of a thousand used to read identically and were
    # judged in the same band, though the first carries several times the sampling error of the
    # second. A flawless reproduction of the right population misses the 15% budget about half
    # the time at twenty subjects (tests/test_population_sampling_cost.py), so the size of that
    # error belongs beside the size of the ensemble.
    assert "sampling error of the 5th band ~10% of the band at 40 subjects" in run.protocol
    bigger = simulate_population(
        _MODEL, "C", duration=6.0, steps=6,
        variability=(SubjectVariability(parameter="V", cv=0.3),), subjects=1000, seed=11,
    )
    assert "~2% of the band at 1000 subjects" in bigger.protocol


def test_a_parameter_whose_variability_could_not_reach_the_run_is_refused() -> None:
    """The silent failure this exists to prevent: the ensemble runs, every subject is identical,
    the bands come out as one line, and nothing says the variability never applied."""
    with pytest.raises(ValueError, match="declares no parameter 'CL'"):
        simulate_population(
            _MODEL, "C", duration=6.0, steps=6,
            variability=(SubjectVariability(parameter="CL", cv=0.3),), subjects=10, seed=1,
        )
    with pytest.raises(ValueError, match="determined by a rule or initial assignment"):
        simulate_population(
            _MODEL, "C", duration=6.0, steps=6,
            variability=(SubjectVariability(parameter="Vd", cv=0.3),), subjects=10, seed=1,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"subjects": 1}, "at least two subjects"),
        ({"variability": ()}, "not a population"),
        ({"percentiles": ()}, "at least one percentile band"),
    ],
)
def test_an_ensemble_that_is_not_a_population_is_refused(kwargs: dict, message: str) -> None:
    call = dict(
        duration=6.0, steps=6, variability=(SubjectVariability(parameter="V", cv=0.3),),
        subjects=10, seed=1,
    )
    call.update(kwargs)
    with pytest.raises(ValueError, match=message):
        simulate_population(_MODEL, "C", **call)  # type: ignore[arg-type]


def test_a_simulated_population_certifies_end_to_end() -> None:
    """Roadmap #7's "done when", with the deferred half no longer supplied by hand: a population
    envelope simulated here, judged against a reference, and certified — qualified, because the
    verdict rests on a reconstructed variability model and on the sampling that produced it.
    """
    spec = SubjectVariability(parameter="V", cv=0.3)
    run = simulate_population(
        _MODEL, "C", duration=12.0, steps=12,
        variability=(spec,), subjects=500, seed=20260827,
    )
    reported = tuple(
        PercentileBand(
            percentile=band.percentile,
            curve=tuple(_closed_form(band.percentile, spec.omega(), t) for t in run.times),
        )
        for band in run.bands
    )
    certificate = certify_population(
        paper=PaperIdentity(title="a one-compartment population figure", doi="10.1/pop"),
        engine_pin=engine_pin(),
        claims=[PopulationClaim(
            claim_id="fig1-envelope", quantity="plasma concentration envelope",
            reported=reported, predicted=run.bands,
            source_location="Fig 1", protocol=run.protocol,
        )],
    )
    assert certificate.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert certificate.assessments[0].protocol == run.protocol
    # The qualification is written down as an assumption naming the sampling, not left as a flag.
    assert any("virtual population" in a.description for a in certificate.assumptions)


@pytest.mark.parametrize("percentiles", [(0.0, 50.0), (50.0, 100.0), (-5.0,)])
def test_a_percentile_that_is_an_extreme_is_refused_before_the_ensemble_runs(
    percentiles: tuple[float, ...],
) -> None:
    """The 0th and 100th are properties of the ensemble's size, not of the population — and
    catching them after 500 runs would name the band rather than the argument."""
    with pytest.raises(ValueError, match=r"open interval \(0, 100\)"):
        simulate_population(
            _MODEL, "C", duration=6.0, steps=6,
            variability=(SubjectVariability(parameter="V", cv=0.3),), subjects=10, seed=1,
            percentiles=percentiles,
        )


def test_two_variability_specs_for_one_parameter_are_refused() -> None:
    """They apply as two overrides and the later wins, so the earlier draw is discarded in
    silence and the CV in force is not the one the protocol would print."""
    with pytest.raises(ValueError, match="repeated: V"):
        simulate_population(
            _MODEL, "C", duration=6.0, steps=6,
            variability=(
                SubjectVariability(parameter="V", cv=0.3),
                SubjectVariability(parameter="V", cv=0.5),
            ),
            subjects=10, seed=1,
        )


def test_a_parameter_with_no_stated_value_has_no_median_to_vary_around() -> None:
    """libSBML reports an unset value as 0.0, and a log-normal multiplier on zero is zero: the
    bands would collapse to one flat line that reads as a population with no variability."""
    valueless = _MODEL.replace(
        '<parameter id="k" value="0.2" constant="true"/>',
        '<parameter id="k" value="0.2" constant="true"/>\n'
        '      <parameter id="F" constant="true"/>',
    )
    with pytest.raises(ValueError, match="states no value for 'F'"):
        simulate_population(
            valueless, "C", duration=6.0, steps=6,
            variability=(SubjectVariability(parameter="F", cv=0.3),), subjects=10, seed=1,
        )
