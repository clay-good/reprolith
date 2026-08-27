"""Re-fitting a model to data, checked against an estimate available in closed form.

`certify_estimation` and `judge_estimation` took the recovered estimate as given; running the
re-fit was the deferred half of roadmap #8. This is that half, and — as with the population
simulator — it is validated against mathematics rather than against itself.

The model is a one-compartment IV bolus, `C(t) = C0·exp(-k·t)`. On exact data, `ln C` is exactly
linear in `t`, so ordinary least squares on the log scale recovers `k` in closed form. The
optimizer here minimizes squared error on the *natural* scale, which is a different objective —
but on data with no noise both have the same minimum, the true value, so the fit has an
independent answer to be right about.

Needs the `engine` extra.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

from reprolith import (  # noqa: E402
    EstimationClaim,
    OverallVerdict,
    PaperIdentity,
    certify_estimation,
    engine_pin,
    refit_parameters,
    simulate,
)

_C0, _K = 10.0, 0.2

_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="one_compartment">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="C0" value="10" constant="true"/>
      <parameter id="k" value="0.2" constant="true"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>C0</ci></math>
      </initialAssignment>
    </listOfInitialAssignments>
    <listOfRules>
      <rateRule variable="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>C</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""

#: Exact observations of the true model, at times that are deliberately *not* on any round grid,
#: so the interpolation the fit relies on is exercised rather than sidestepped.
_DATA = tuple(
    (t, _C0 * math.exp(-_K * t)) for t in (0.7, 1.3, 2.9, 4.1, 6.5, 8.2, 11.4, 14.9)
)


def _closed_form_k() -> float:
    """The exact `k` behind the data: the slope of ln C against t, which is linear with no noise."""
    n = len(_DATA)
    mean_t = sum(t for t, _ in _DATA) / n
    mean_y = sum(math.log(c) for _, c in _DATA) / n
    covariance = sum((t - mean_t) * (math.log(c) - mean_y) for t, c in _DATA)
    variance = sum((t - mean_t) ** 2 for t, _ in _DATA)
    return -covariance / variance


def test_the_refit_recovers_the_parameter_the_data_came_from() -> None:
    """Started 2.5x away from the truth, so a fit that merely returned its starting value fails."""
    assert _closed_form_k() == pytest.approx(_K, rel=1e-9)
    result = refit_parameters(
        _MODEL, "C", observations=_DATA, start=(("k", 0.5),), dataset="synthetic exact data"
    )
    assert result.value("k") == pytest.approx(_closed_form_k(), rel=1e-3)
    assert result.objective < 1e-6


def test_two_parameters_are_recovered_together() -> None:
    """A one-parameter fit can hide a bias in the other; both moving is the real case."""
    result = refit_parameters(
        _MODEL, "C", observations=_DATA, start=(("C0", 4.0), ("k", 0.5)),
    )
    assert result.value("C0") == pytest.approx(_C0, rel=2e-3)
    assert result.value("k") == pytest.approx(_K, rel=2e-3)


def test_the_same_data_and_starting_values_give_the_same_estimate() -> None:
    """No randomness anywhere in the method: the initial simplex, the coefficients, and the
    convergence test are all fixed, so an estimate is a function of its inputs."""
    kwargs = dict(observations=_DATA, start=(("k", 0.5),))
    first = refit_parameters(_MODEL, "C", **kwargs)  # type: ignore[arg-type]
    again = refit_parameters(_MODEL, "C", **kwargs)  # type: ignore[arg-type]
    assert first == again


def test_the_protocol_names_all_four_things_a_refit_depends_on() -> None:
    result = refit_parameters(
        _MODEL, "C", observations=_DATA, start=(("k", 0.5),), dataset="Table 3 plasma samples"
    )
    for expected in ("ordinary least squares", "Table 3 plasma samples", "8 observations",
                     "Nelder-Mead on the log scale", "k=0.5", "converged in",
                     "uniform grid", "interpolated", "read=[C]"):
        assert expected in result.protocol, result.protocol


def test_a_fit_that_did_not_converge_is_refused_not_reported() -> None:
    """An optimizer that stopped early has not produced an estimate. Publishing where it happened
    to be is exactly the failure the estimation path exists to avoid."""
    with pytest.raises(ValueError, match="did not converge in 3 iterations"):
        refit_parameters(
            _MODEL, "C", observations=_DATA, start=(("k", 5.0),), max_iterations=3
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"start": (("k", 0.0),)}, "must be positive"),
        ({"start": (("k", 0.5), ("k", 0.6))}, "estimated once"),
        ({"start": ()}, "at least one parameter"),
        ({"start": (("CL", 0.5),)}, "not in the model"),
        ({"observations": ((1.0, 5.0),), "start": (("C0", 4.0), ("k", 0.5))}, "cannot identify"),
        ({"observations": ((-1.0, 5.0), (2.0, 3.0))}, "negative time"),
        ({"observations": ((0.0, 10.0), (0.0, 10.0))}, "no trajectory is being fitted"),
    ],
)
def test_a_fit_that_could_not_mean_anything_is_refused(kwargs: dict, message: str) -> None:
    call: dict = dict(observations=_DATA, start=(("k", 0.5),))
    call.update(kwargs)
    with pytest.raises(ValueError, match=message):
        refit_parameters(_MODEL, "C", **call)


def test_a_recovered_estimate_certifies_end_to_end() -> None:
    """Roadmap #8's "done when", with the deferred half no longer supplied by hand: an estimate
    re-derived from data here, judged against the paper's reported value, and certified as an
    estimation verdict distinct from a simulation one."""
    result = refit_parameters(
        _MODEL, "C", observations=_DATA, start=(("k", 0.5),), dataset="Table 3 plasma samples"
    )
    certificate = certify_estimation(
        paper=PaperIdentity(title="a one-compartment estimate", doi="10.1/est"),
        engine_pin=engine_pin(),
        claims=[EstimationClaim(
            claim_id="k-estimate", quantity="elimination rate constant",
            reported=_K, recovered=result.value("k"),
            source_location="Table 2", protocol=result.protocol,
        )],
    )
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert certificate.assessments[0].protocol == result.protocol


def test_the_fitted_trajectory_is_the_one_the_data_came_from() -> None:
    """The estimate is only as good as what it makes the model do, so this checks the model at the
    recovered value reproduces the observations rather than only that a number came out close."""
    result = refit_parameters(_MODEL, "C", observations=_DATA, start=(("k", 0.5),))
    from reprolith.certify import _apply_overrides

    times, values = simulate(
        _apply_overrides(_MODEL, (("k", result.value("k")),)), "C", duration=15.0, steps=150
    )
    for time, observed in _DATA:
        index = min(range(len(times)), key=lambda i: abs(times[i] - time))
        assert values[index] == pytest.approx(observed, rel=0.02)


def test_a_parameter_the_data_cannot_identify_is_refused_not_estimated() -> None:
    """The quiet failure this exists to catch, found by auditing this module's own first version.

    Nelder-Mead on a flat landscape shrinks its simplex until the convergence test passes and
    returns the point it started from — reporting "converged in N iterations" over a residual that
    never improved. The caller's starting guess then reaches the certificate as a recovered
    estimate, with a protocol saying a fit produced it.
    """
    unidentifiable = _MODEL.replace(
        '<parameter id="k" value="0.2" constant="true"/>',
        '<parameter id="k" value="0.2" constant="true"/>\n'
        '      <parameter id="unused" value="1" constant="true"/>',
    )
    with pytest.raises(ValueError, match="does not identify them"):
        refit_parameters(
            unidentifiable, "C", observations=_DATA, start=(("unused", 1.0),),
        )
