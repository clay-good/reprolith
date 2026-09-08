"""Every claim type this engine has can publish the failure it earns, rather than raising.

The contract is one line long and this repository has broken it twice. A non-pass verdict must
carry a root-cause attribution — the oracle refuses one without it — so a front end that does not
supply a fallback cause *raises* when a claim misses. Both times the effect was the same and worse
than a wrong number: the path could publish a reproduction or nothing at all, and a class's
agreement rate could not have come out any other way.

> "Without a fallback cause an objective that misses raises instead of certifying, so this path
> could publish a reproduction or nothing at all — and the class's agreement rate could not have
> come out any other way." (`certify_constraint_based`)

> "A failed verdict must carry a root cause, and a claim that supplies none used to raise instead
> of certifying — so a seed that happened to miss crashed the run rather than producing the honest
> not-reproduced certificate it had earned." (`certify_stochastic`)

Both were found one front end at a time, after the fact. This is the differential: every claim type,
driven through its own front end with a reported value that is wrong, asserting that what comes back
is a **certificate carrying a root cause** — and, for the same claims, that the certificate names
what the verdict rests on in a protocol line, since a published number nobody can re-run is not
evidence.

New claim types are added to `_MISSES` as they are built. A front end reached by no entry here is a
front end this check does not cover, which is why the list is asserted against the front ends the
package exports rather than left to be remembered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from reprolith import (
    Certificate,
    EstimationClaim,
    LogicalClaim,
    NoiseClaim,
    NoiseStatistic,
    PaperIdentity,
    PercentileBand,
    PopulationClaim,
    Reaction,
    ReportedBasin,
    StochasticClaim,
    UpdateScheme,
    certify_estimation,
    certify_logical,
    certify_population,
    certify_stochastic,
)
from reprolith.enums import OverallVerdict, Verdict
from reprolith.logical import solver_pin as logical_pin
from reprolith.spatial import (
    FrontSpeedClaim,
    GradientClaim,
    PatternClaim,
    SpatialClaim,
    certify_spatial,
)
from reprolith.spatial import solver_pin as spatial_pin
from reprolith.stochastic import ExtinctionTimeClaim
from reprolith.stochastic import solver_pin as stochastic_pin

_PAPER = PaperIdentity(title="a paper whose number is wrong", doi="")

# --- one wrong claim per type, each through its own front end -------------------------------------

_TOGGLE = {"A": "!B", "B": "!A"}
_IMMIGRATION_DEATH = [Reaction(10.0, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())]


def _logical_steady_state() -> Certificate:
    return certify_logical(
        paper=_PAPER, engine_pin=logical_pin(),
        claims=[LogicalClaim(
            claim_id="miss", quantity="steady state", rules=_TOGGLE,
            reported={"A": 1, "B": 1},  # a 2-cycle state, not a fixed point
            source_location="Fig 1",
        )],
    )


def _logical_attractor_set() -> Certificate:
    return certify_logical(
        paper=_PAPER, engine_pin=logical_pin(),
        claims=[LogicalClaim(
            claim_id="miss", quantity="attractor set", rules=_TOGGLE, reported={},
            attractors=[[{"A": 1, "B": 0}]],  # one of the three
            source_location="Fig 1", scheme=UpdateScheme.SYNCHRONOUS,
        )],
    )


def _logical_basin() -> Certificate:
    return certify_logical(
        paper=_PAPER, engine_pin=logical_pin(),
        claims=[LogicalClaim(
            claim_id="miss", quantity="basin", rules=_TOGGLE, reported={},
            basin=ReportedBasin(attractor=[{"A": 1, "B": 0}], states=4),  # it is 1
            source_location="Fig 1", scheme=UpdateScheme.SYNCHRONOUS,
        )],
    )


def _stochastic_mean() -> Certificate:
    return certify_stochastic(
        paper=_PAPER, engine_pin=stochastic_pin(),
        n_species=1, reactions=_IMMIGRATION_DEATH, initial=[0],
        claims=[StochasticClaim(
            claim_id="miss", quantity="mean copy number", species=0,
            reported_mean=40.0,  # the stationary mean is 10
            source_location="Table 1", duration=40.0, trajectories=400, seed=11,
        )],
    )


def _stochastic_extinction() -> Certificate:
    return certify_stochastic(
        paper=_PAPER, engine_pin=stochastic_pin(),
        n_species=1, reactions=[Reaction(1.0, ((0, 1),), ())], initial=[5],
        extinctions=[ExtinctionTimeClaim(
            claim_id="miss", quantity="mean time to extinction", species=0,
            reported_mean=20.0,  # H(5)/k is about 2.28
            source_location="Table 1", trajectories=400, seed=11, max_time=1e6,
        )],
    )


def _stochastic_noise() -> Certificate:
    return certify_stochastic(
        paper=_PAPER, engine_pin=stochastic_pin(),
        n_species=1, reactions=_IMMIGRATION_DEATH, initial=[0],
        noises=[NoiseClaim(
            claim_id="miss", quantity="Fano factor", species=0,
            statistic=NoiseStatistic.FANO_FACTOR,
            reported_value=3.0,  # Poisson statistics give 1
            source_location="Fig 2", duration=40.0, trajectories=4000, seed=11,
        )],
    )


def _spatial_profile() -> Certificate:
    points, dx = 60, 1.0
    initial = tuple(100.0 if index == points // 2 else 0.0 for index in range(points))
    return certify_spatial(
        paper=_PAPER, engine_pin=spatial_pin(),
        claims=[SpatialClaim(
            claim_id="miss", quantity="profile", initial=initial,
            reference=tuple(1.0 for _ in range(points)),  # a flat line the diffusion never gives
            source_location="Fig 1", diffusivity=1.0, dx=dx, dt=0.2 * dx * dx, steps=50,
        )],
    )


def _spatial_gradient() -> Certificate:
    dx = 0.1
    return certify_spatial(
        paper=_PAPER, engine_pin=spatial_pin(),
        gradients=[GradientClaim(
            claim_id="miss", quantity="decay length",
            reported=20.0,  # sqrt(D/k) is 2
            source_location="Fig 3", source=100.0, diffusivity=1.0, decay=0.25,
            dx=dx, points=300, dt=0.2 * dx * dx, steps=40000, fit_from=20, fit_to=120,
        )],
    )


def _spatial_front() -> Certificate:
    dx, window = 0.5, 2000
    initial = tuple(1.0 if index * dx < 20.0 else 0.0 for index in range(400))
    return certify_spatial(
        paper=_PAPER, engine_pin=spatial_pin(),
        fronts=[FrontSpeedClaim(
            claim_id="miss", quantity="front speed",
            reported=20.0,  # 2*sqrt(rD) is 2
            source_location="Table 2", initial=initial, diffusivity=1.0, growth=1.0,
            dx=dx, dt=0.2 * dx * dx, settle_steps=window, measure_steps=window,
        )],
    )


def _spatial_pattern() -> Certificate:
    length, dx = 160.0, 0.5
    return certify_spatial(
        paper=_PAPER, engine_pin=spatial_pin(),
        patterns=[PatternClaim(
            claim_id="miss", quantity="Turing wavelength",
            reported=80.0,  # the mode this network selects is about 16
            source_location="Fig 4", kinetics="schnakenberg", a=0.1, b=0.9,
            du=1.0, dv=40.0, length=length, points=int(round(length / dx)) + 1,
            dt=0.0015, steps=6000, confirm_steps=2000,
        )],
    )


def _population_envelope() -> Certificate:
    times = (0.0, 1.0, 2.0)
    reported = tuple(
        PercentileBand(percentile=p, curve=tuple(10.0 * f for f in (1.0, 0.8, 0.6)))
        for p in (5.0, 50.0, 95.0)
    )
    predicted = tuple(
        PercentileBand(percentile=p, curve=tuple(100.0 for _ in times))  # ten times the paper's
        for p in (5.0, 50.0, 95.0)
    )
    return certify_population(
        paper=_PAPER, engine_pin=stochastic_pin(),
        claims=[PopulationClaim(
            claim_id="miss", quantity="envelope", reported=reported, predicted=predicted,
            source_location="Fig 2", protocol="500 subjects, seed 1",
        )],
    )


def _population_variability() -> Certificate:
    import math
    from statistics import NormalDist

    from reprolith import VariabilityClaim
    from reprolith.oracle import SpreadStatistic

    omega = math.sqrt(math.log(1.0 + 0.3**2))
    normal = NormalDist()
    values = tuple(
        10.0 * math.exp(omega * normal.inv_cdf((index + 0.5) / 1500)) for index in range(1500)
    )
    return certify_population(
        paper=_PAPER, engine_pin=stochastic_pin(),
        variability=[VariabilityClaim(
            claim_id="miss", quantity="between-subject CV of AUC",
            statistic=SpreadStatistic.COEFFICIENT_OF_VARIATION,
            reported=0.9,  # the population's own CV is 0.3
            values=values, source_location="Table 4",
            protocol="1500 subjects, seed 1, log-normal variability on V (CV 0.3)",
        )],
    )


def _estimation() -> Certificate:
    return certify_estimation(
        paper=_PAPER, engine_pin=stochastic_pin(),
        claims=[EstimationClaim(
            claim_id="miss", quantity="clearance", reported=1.0, recovered=9.0,
            source_location="Table 3",
            protocol="least squares, Nelder-Mead from CL=0.5, over the paper's eight observations",
        )],
    )


#: Every claim type reachable without an optional extra, and the front end each goes through. The
#: ones behind an extra are covered below.
_MISSES: dict[str, Callable[[], Certificate]] = {
    "logical steady state": _logical_steady_state,
    "logical attractor set": _logical_attractor_set,
    "logical basin": _logical_basin,
    "stochastic mean": _stochastic_mean,
    "stochastic first passage": _stochastic_extinction,
    "stochastic noise statistic": _stochastic_noise,
    "spatial profile": _spatial_profile,
    "spatial gradient": _spatial_gradient,
    "spatial front speed": _spatial_front,
    "spatial pattern": _spatial_pattern,
    "population envelope": _population_envelope,
    "population variability metric": _population_variability,
    "parameter estimate": _estimation,
}


# --- the claim types behind an optional extra, driven the same way -------------------------------
#
# Excusing them to other test files is what the list above says it must not do: those files check
# the claim type they were written for, and none of them asks the question this one asks. So they
# are here, gated on the extra each needs rather than on a promise that somebody else checks them.

_CB = Path(__file__).parent.parent / "datasets" / "constraint_based"


def _fba_certificate(**kwargs) -> Certificate:
    import json

    from reprolith.constraint_based import certify_constraint_based
    from reprolith.fba import solver_pin as fba_pin
    from reprolith.persistence import dossier_from_dict

    return certify_constraint_based(
        dossier_from_dict(
            json.loads((_CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
        ),
        sbml=(_CB / "e_coli_core.xml").read_text(encoding="utf-8"),
        paper=_PAPER, engine_pin=fba_pin(), **kwargs,
    )


def _fba_essentiality() -> Certificate:
    from reprolith.constraint_based import EssentialityClaim
    from reprolith.fba import EssentialKind, ReportedEssentialSet

    return _fba_certificate(essentiality=[EssentialityClaim(
        claim_id="miss", quantity="essential genes",
        reported=ReportedEssentialSet(kind=EssentialKind.GENES, count=40),  # there are seven
        source_location="Table 2",
    )])


def _fba_flux() -> Certificate:
    from reprolith.constraint_based import FluxClaim

    return _fba_certificate(fluxes=[FluxClaim(
        claim_id="miss", quantity="aconitase flux", reaction_id="R_ACONTa",
        reported=60.0,  # the interval pins it at about 6
        source_location="Table 3",
    )])


def _fba_flux_range() -> Certificate:
    from reprolith.constraint_based import FluxRangeClaim

    return _fba_certificate(flux_ranges=[FluxRangeClaim(
        claim_id="miss", quantity="SUCDi range", reaction_id="R_SUCDi",
        reported_min=0.0, reported_max=5.0,  # it runs from 5.06 to 1000
        source_location="Table 3",
    )])


def _pkpd_scalar() -> Certificate:
    from reprolith import Claim, certify_model
    from reprolith.engine import engine_pin

    return certify_model(
        _ONE_COMPARTMENT, paper=_PAPER, engine_pin=engine_pin(),
        claims=[Claim(
            claim_id="miss", quantity="peak concentration", species="C",
            reported=1000.0,  # the model peaks at 10
            source_location="Table 1", metric="cmax",
        )],
        duration=12.0, steps=12,
    )


def _pkpd_curve() -> Certificate:
    from reprolith import CurveClaim, certify_curves
    from reprolith.engine import engine_pin

    return certify_curves(
        _ONE_COMPARTMENT, paper=_PAPER, engine_pin=engine_pin(),
        claims=[CurveClaim(
            claim_id="miss", quantity="concentration time course", species="C",
            reference=tuple(1000.0 for _ in range(13)),  # a flat line a hundred times too high
            source_location="Fig 1", duration=12.0, steps=12,
        )],
    )


#: A one-compartment IV bolus: C(0) = D/V = 10, eliminated at k = 0.2.
_ONE_COMPARTMENT = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="one_compartment">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false" initialAmount="10"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.2" constant="true"/></listOfParameters>
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

_BEHIND_AN_EXTRA: dict[str, tuple[str, Callable[[], Certificate]]] = {
    "constraint-based essential set": ("scipy", _fba_essentiality),
    "constraint-based flux": ("scipy", _fba_flux),
    "constraint-based flux range": ("scipy", _fba_flux_range),
    "pk/pd scalar metric": ("COPASI", _pkpd_scalar),
    "pk/pd curve": ("COPASI", _pkpd_curve),
}


@pytest.mark.parametrize("name", sorted(_BEHIND_AN_EXTRA))
def test_a_wrong_claim_publishes_a_verdict_behind_an_extra_too(name: str) -> None:
    extra, build = _BEHIND_AN_EXTRA[name]
    pytest.importorskip(extra, reason=f"{name} needs an optional extra that is not installed")
    if extra == "scipy":
        pytest.importorskip("libsbml", reason="the constraint-based path needs python-libsbml")
    certificate = build()
    assert certificate.overall is not OverallVerdict.REPRODUCED, name
    assessment = certificate.assessments[-1]
    assert assessment.root_cause, f"{name}: published with no root cause"
    assert assessment.protocol, f"{name}: published with no protocol line"


@pytest.mark.parametrize("name", sorted(_MISSES))
def test_a_wrong_claim_publishes_a_verdict_rather_than_raising(name: str) -> None:
    """The contract, one claim type at a time. A miss is a result, not an exception."""
    certificate = _MISSES[name]()
    assert certificate.overall is not OverallVerdict.REPRODUCED, name
    assessment = certificate.assessments[0]
    # An abstention is a legitimate answer for some of these — a spatial claim whose step is too
    # coarse, an ensemble that cannot resolve its claim — but a *judged* miss must name a cause.
    if assessment.verdict in (Verdict.PARTIAL, Verdict.FAILED):
        assert assessment.root_cause, f"{name}: a judged miss with no root cause"
    else:
        assert assessment.verdict is Verdict.NOT_EVALUABLE, name
        assert assessment.root_cause, f"{name}: an abstention that does not say why"


@pytest.mark.parametrize("name", sorted(_MISSES))
def test_every_published_assessment_says_what_its_verdict_rests_on(name: str) -> None:
    """A number nobody can re-run is not evidence, so each front end records its own protocol."""
    assessment = _MISSES[name]().assessments[0]
    assert assessment.protocol, f"{name}: published with no protocol line"


def test_the_scope_flag_is_on_every_one_of_them() -> None:
    """The one sentence no certificate may be published without, from any front end."""
    for name, build in _MISSES.items():
        certificate = build()
        assert certificate.scope.machine == "reproducible-not-correct-not-clinical", name


def test_this_matrix_covers_every_claim_type_the_package_exports() -> None:
    """The list is the check's weakness, so it is held to the package rather than to memory.

    A claim type added without an entry here is one this differential does not cover, and the
    failure it would have caught is the one that has already happened twice.
    """
    import reprolith

    exported = {
        name for name in reprolith.__all__
        if name.endswith("Claim") and name not in {"UnattemptedClaim", "DossierClaim"}
    }
    covered = {
        "LogicalClaim", "StochasticClaim", "ExtinctionTimeClaim", "NoiseClaim",
        "PopulationClaim", "EstimationClaim", "VariabilityClaim",
        "SpatialClaim", "GradientClaim", "FrontSpeedClaim", "PatternClaim",
        # Covered too, behind the extra each needs — see `_BEHIND_AN_EXTRA`. The constraint-based
        # claim types are not in this `__all__` at all (they live in `reprolith.constraint_based`)
        # and are covered there as well.
        "Claim", "CurveClaim",
    }
    from reprolith.constraint_based import EssentialityClaim, FluxClaim, FluxRangeClaim

    assert {EssentialityClaim, FluxClaim, FluxRangeClaim}  # named, so a rename fails here
    assert exported == covered, (
        "a claim type is exported that this differential neither covers nor excuses: "
        f"{sorted(exported - covered)}"
    )
