"""Cross-engine corroboration: COPASI vs libRoadRunner (spec: simulation-oracle).

Running the same model under two independently-implemented engines and comparing trajectories turns
"engine-sensitive" from a hidden risk into a reported result. Needs both the ``engine`` (COPASI) and
``corroborate`` (libRoadRunner) extras; skips without either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")
pytest.importorskip("roadrunner", reason="the optional 'corroborate' extra (libRoadRunner) is not installed")

from reprolith import corroborate_curve, roadrunner_pin, simulate_with_roadrunner  # noqa: E402

_KIN = Path(__file__).parent.parent / "datasets" / "kinetic"
_MODELS = {m["id"]: m for m in json.loads((_KIN / "cross_validation.json").read_text(encoding="utf-8"))["models"]}
_SBML = (_KIN / "BIOMD0000000010.xml").read_text(encoding="utf-8")


@pytest.mark.parametrize("model_id", sorted(_MODELS))
def test_verdict_is_engine_independent_across_the_kinetic_class(model_id: str) -> None:
    # Verdict stability reported across two engines for every supported kinetic model (roadmap #5):
    # COPASI and libRoadRunner land on the same trajectory, so each verdict is the model's, not a
    # single solver's.
    spec = _MODELS[model_id]
    result = corroborate_curve(
        (_KIN / f"{model_id}.xml").read_text(encoding="utf-8"),
        spec["species"], duration=spec["duration"], steps=spec["steps"],
    )
    assert result.engines == ("copasi", "roadrunner")
    assert result.stable
    assert "engine-independent" in result.summary()


def test_an_impossibly_tight_tolerance_reports_engine_sensitive() -> None:
    # The stable/sensitive decision responds to the declared tolerance: with zero tolerance even the
    # ~1e-7 solver difference is flagged, exercising the engine-sensitive branch honestly.
    result = corroborate_curve(_SBML, "MAPK_PP", duration=4000.0, steps=200, rel_tol=0.0)
    assert not result.stable
    assert "engine-sensitive" in result.summary()


def test_roadrunner_backend_matches_the_grid_and_carries_a_pin() -> None:
    times, values = simulate_with_roadrunner(_SBML, "MAPK_PP", duration=4000.0, steps=200)
    assert len(times) == len(values) == 201
    assert times[0] == 0.0 and times[-1] == pytest.approx(4000.0)
    pin = roadrunner_pin()
    assert pin.engine == "roadrunner" and pin.version


def test_the_published_distance_is_a_bound_the_engines_can_reproduce() -> None:
    """Five figures of a distance between two agreeing engines is not a measurement.

    COPASI is not bit-identical across repeated calls in one process — a period-2 alternation at
    about 1e-11 relative — and the distance between two engines that agree is a difference of
    nearly-equal numbers, so that noise is amplified into the leading digits. On one committed
    model it moved the distance by 8% between runs, and it moves further between machines: a
    one-significant-figure bound of 4e-07 taken here was exceeded on CI at 4.55e-07. The published
    granularity is therefore the decade, rounded up, so it never claims better agreement than was
    measured and a second machine reproduces it — and the distance is lifted by a margin first, so
    a value sitting near a decade boundary does not land on either side of it by chance.
    """
    from reprolith.corroboration import EngineCorroboration

    def bound(distance: float) -> float:
        return EngineCorroboration(
            species="X", engines=("copasi", "roadrunner"), distance=distance, stable=True
        ).distance_bound()

    assert bound(2.328e-06) == bound(2.143e-06) == 1e-05  # the pair that moved 8% between runs
    assert bound(3.2e-04) == 1e-03
    assert bound(3.515e-07) == bound(4.551e-07) == 1e-06  # this machine's value, and CI's
    # The decade alone was not enough for a distance sitting near a boundary. Metformin measures
    # 1.11e-07 in isolation and just under 1e-07 inside a longer run, so three runs of one
    # milestone script on one machine published 1e-06 twice and 1e-07 once. Lifting the distance
    # by the margin before rounding puts both draws on the same side of the boundary.
    assert bound(9.9e-08) == bound(1.11e-07) == 1e-06
    assert bound(1.0e-05) == 1e-04  # a decade of looseness is the price; it never rounds down
    assert bound(0.0) == 0.0

    # And it is genuinely an upper bound on every model in the committed corpus.
    committed = json.loads((_KIN / "milestone" / "corroboration.json").read_text(encoding="utf-8"))
    for model_id, record in committed.items():
        spec = _MODELS[model_id]
        result = corroborate_curve(
            (_KIN / f"{model_id}.xml").read_text(encoding="utf-8"),
            spec["species"], duration=spec["duration"], steps=spec["steps"],
        )
        assert result.distance <= record["distance_at_most"]


_PKPD = Path(__file__).parent.parent / "datasets"
_METFORMIN = _PKPD / "worked_examples" / "Zake2021_metformin_human_single_PO.xml"


def test_the_pkpd_claims_are_engine_independent_at_the_doses_they_were_certified_at() -> None:
    """Roadmap #5, second class: PK/PD verdicts no longer rest, as far as any artifact showed, on
    a single solver.

    The overrides matter. Without them only the model's default arm is checkable, and for this
    reconstruction that is one of its two claims — the other runs at 779.9 mg free base.
    """
    model = _METFORMIN.read_text(encoding="utf-8")
    for overrides in ((), (("Metformin_Dose_in_Lumen_in_mg", 779.9),)):
        result = corroborate_curve(
            model, "mPlasmaVenous", duration=24.0, steps=480, overrides=overrides
        )
        assert result.stable, result.summary()


def test_an_override_that_would_not_take_effect_is_refused_here_too() -> None:
    """Corroboration applies overrides through the same function certification does, so a value
    that cannot reach the run is refused rather than corroborated as if it had."""
    model = _METFORMIN.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="not in the model"):
        corroborate_curve(
            model, "mPlasmaVenous", duration=24.0, steps=480,
            overrides=(("no_such_parameter", 1.0),),
        )


def test_overriding_the_dose_actually_changes_the_curve() -> None:
    """A corroboration of two identical runs proves nothing about the override, so this checks the
    arms are in fact different before the engine comparison is allowed to mean anything."""
    from reprolith import simulate
    from reprolith.certify import _apply_overrides

    model = _METFORMIN.read_text(encoding="utf-8")
    _, base = simulate(model, "mPlasmaVenous", duration=24.0, steps=480)
    _, dosed = simulate(
        _apply_overrides(model, (("Metformin_Dose_in_Lumen_in_mg", 779.9),)),
        "mPlasmaVenous", duration=24.0, steps=480,
    )
    assert max(dosed) > 1.5 * max(base)


def test_a_model_reprolith_built_is_engine_independent_too() -> None:
    """Every corroboration in this file, and every one in the committed artifacts, is of a model
    an *author* shipped. A model Reprolith assembled from a dossier had never been checked.

    That matters twice over. It is the reconstruction path's own engine independence — the thing
    the certificates claim — and it is a third implementation reading what `build_model_sbml`
    writes. libSBML both writes and validates that file, so libSBML agreeing with it is not
    independent evidence; COPASI running it is one outside reader, and libRoadRunner is a second.
    """
    from reprolith import (
        Dossier,
        Equation,
        ExtractionConfidence,
        Parameter,
        build_model_sbml,
    )

    dossier = Dossier(
        entry="two_compartment",
        state_variables=("central", "peripheral"),
        equations=(
            Equation(target="central", expression="-(k12 + k10) * central + k21 * peripheral",
                     source_location="Eq 1"),
            Equation(target="peripheral", expression="k12 * central - k21 * peripheral",
                     source_location="Eq 2"),
        ),
        parameters=tuple(
            Parameter(name=name, value=value, unit="1/h", source_location="Table 1",
                      confidence=ExtractionConfidence.QUOTED)
            for name, value in (("k12", 0.8), ("k21", 0.3), ("k10", 0.25))
        ),
        initial_conditions=(
            Parameter(name="central", value=100.0, unit="mg", source_location="Methods",
                      confidence=ExtractionConfidence.QUOTED),
            Parameter(name="peripheral", value=0.0, unit="mg", source_location="Methods",
                      confidence=ExtractionConfidence.QUOTED),
        ),
    )

    built = build_model_sbml(dossier)
    for species in ("central", "peripheral"):
        result = corroborate_curve(built, species, duration=24.0, steps=240)
        assert result.stable, result.summary()


def test_the_published_bound_does_not_move_between_two_measurements_of_one_run() -> None:
    """The committed artifact used to oscillate, and this is the claim that it no longer can.

    COPASI alternates in its last places within one process, so a single draw's distance moves by
    about 13% between consecutive calls on this model's muscle curve — 4.89e-08 against 5.53e-08.
    `distance_bound`'s fixed margin lifts those to either side of 1e-07, so three regenerations of
    the PK/PD milestone published 1e-06, then 1e-07, then 1e-06 for one claim. A fixed margin
    cannot fix that in general: whatever it is, some pair of phases straddles a boundary after it.

    Measuring twice and publishing the worst does, because the alternation is period-two. This
    calls the whole path repeatedly and requires one number, which is the property the committed
    file needs and the one no test held.
    """
    sbml = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.xml"
    ).read_text(encoding="utf-8")
    bounds = {
        corroborate_curve(sbml, "mMuscle", duration=24.0, steps=480).distance_bound()
        for _ in range(3)
    }
    assert len(bounds) == 1, f"the published bound moved between runs: {sorted(bounds)}"


def test_one_draw_can_be_asked_for_and_never_states_better_agreement() -> None:
    """The worst of several measurements is weaker than any single one, never stronger — so the
    default cannot turn an engine-sensitive result into an engine-independent one.

    Compared at the *bound*, which is what gets published, and at the raw distance only up to the
    solver's own last places. `single` and `doubled` are two separate invocations, so the draw one
    takes and the draws the other maximizes over are different calls into COPASI — and where the
    alternation's two phases nearly coincide, which phase lands first decides the last digit. This
    assertion demanded an exact ordering across invocations that the engine does not offer, and it
    failed in CI on a pair 6e-07 apart in relative terms. The defect it exists to catch — a `min`
    where the `max` belongs — is a 13% drop on this curve, which the slack below cannot hide.
    """
    sbml = (
        Path(__file__).parent.parent / "datasets" / "worked_examples"
        / "Zake2021_metformin_human_single_PO.xml"
    ).read_text(encoding="utf-8")
    single = corroborate_curve(sbml, "mMuscle", duration=24.0, steps=480, draws=1)
    doubled = corroborate_curve(sbml, "mMuscle", duration=24.0, steps=480, draws=2)
    assert doubled.distance_bound() >= single.distance_bound()
    assert doubled.distance >= single.distance * (1.0 - 1e-4)
    with pytest.raises(ValueError, match="at least one draw"):
        corroborate_curve(sbml, "mMuscle", duration=24.0, steps=480, draws=0)
