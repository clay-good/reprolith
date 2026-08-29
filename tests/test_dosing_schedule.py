"""A claim whose protocol is more than one administration (bootstrap task 3.x, PK/PD).

The metformin paper validates its human model against four published datasets, and two of them
give the main dose a **pre-dose twelve hours earlier**. Run as a single administration those two
read 15.2% and 7.6% away from what the paper reports — two `not-reproduced` verdicts against a
model that reproduces them perfectly well. A claim's `parameter_overrides` cannot say "and 375 mg
twelve hours before this", so the shape, not the model or the paper, was the blocker.

A schedule is a sequence of segments run in order: each one is the author's own model with its own
parameter values, started from the state the previous segment ended in, so **the model's own dose
event administers every dose** and nothing is added to it. The claim is read over the last segment;
the ones before condition it.

Needs the `engine` extra; the cross-engine test also needs `corroborate`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")

from reprolith import Claim, PaperIdentity, Verdict, certify_model  # noqa: E402
from reprolith.certify import _metric, _run_schedule  # noqa: E402
from reprolith.engine import engine_pin, simulate  # noqa: E402

_MODEL = (
    Path(__file__).parent.parent / "datasets" / "worked_examples"
    / "Zake2021_metformin_human_single_PO.xml"
).read_text(encoding="utf-8")

_DOSE = "Metformin_Dose_in_Lumen_in_mg"
_FREE_BASE = 129.16 / 165.62  # metformin HCl to free base


def _hcl(mg: float) -> float:
    return round(mg * _FREE_BASE, 2)


def _arm(pre: float, main: float) -> tuple[tuple[float, tuple[tuple[str, float], ...]], ...]:
    return ((12.0, ((_DOSE, _hcl(pre)),)), (24.0, ((_DOSE, _hcl(main)),)))


@pytest.mark.parametrize(
    ("pre", "main", "reported", "alone"),
    [(375, 250, 3.9, 3.3091), (500, 750, 9.4, 8.6816)],
    ids=["Chung 250 mg", "Wen 750 mg"],
)
def test_a_pre_dose_is_what_makes_the_paper_s_number_reproduce(
    pre: float, main: float, reported: float, alone: float
) -> None:
    """Both arms, against the values the paper prints and the values the dose alone gives."""
    times, values = _run_schedule(_MODEL, "mPlasmaVenous", schedule=_arm(pre, main), steps=1200)
    with_pre_dose = _metric(times, values, "cmax")
    assert with_pre_dose == pytest.approx(reported, rel=0.05)
    # And the failure it repairs is real: the same dose without the pre-dose misses by far more.
    assert abs(alone - reported) / reported > 0.05


def test_a_one_segment_schedule_is_the_ordinary_run() -> None:
    """The new path must not change the old answer, or every committed claim moves under it."""
    schedule = ((24.0, ((_DOSE, 389.92),)),)
    times, values = _run_schedule(_MODEL, "mPlasmaVenous", schedule=schedule, steps=480)
    plain_times, plain_values = simulate(_MODEL, "mPlasmaVenous", duration=24.0, steps=480)
    assert times == plain_times
    # Not bit-identical, and the gap is not the same size everywhere. COPASI differs across
    # repeated calls in one process (see `simulate`), and how much depends on the build: this
    # agreed to 1e-11 locally and to 1.2e-9 and 1.7e-7 on two of CI's interpreters. A tolerance
    # fitted to one machine is a threshold with no basis, so this one is set where the *claim*
    # lives — the failure it must catch is the segment being dropped, which moves the answer by
    # 15%, not by parts in ten million.
    assert max(values) == pytest.approx(max(plain_values), rel=1e-5)


def test_the_carried_state_is_an_amount_not_a_concentration() -> None:
    """The bug this was written with, and the one that hides best.

    `simulate` returns concentrations and a species' state variable here is an amount, so writing
    the concentration into the next segment's initial amount divides the carried state by the
    compartment volume — 2247 mL for this model's venous plasma. Nothing fails and nothing warns:
    the prior dose simply vanishes, and the answer comes back exactly equal to the no-pre-dose
    one. That is what this asserts against.
    """
    times, values = _run_schedule(_MODEL, "mPlasmaVenous", schedule=_arm(375, 250), steps=1200)
    scheduled = _metric(times, values, "cmax")
    alone = max(simulate(
        __import__("reprolith").certify._apply_overrides(_MODEL, ((_DOSE, _hcl(250)),)),
        "mPlasmaVenous", duration=24.0, steps=1200,
    )[1])
    assert scheduled > alone * 1.10, (scheduled, alone)


def test_a_claim_states_a_schedule_or_overrides_and_not_both() -> None:
    """Carrying both leaves it unsaid which segment the overrides belong to."""
    with pytest.raises(ValueError, match="not both"):
        Claim(
            claim_id="x", quantity="q", species="mPlasmaVenous", reported=1.0,
            source_location="Table 5", schedule=_arm(375, 250),
            parameter_overrides=((_DOSE, 1.0),),
        )


def test_a_segment_must_run_for_a_positive_time() -> None:
    with pytest.raises(ValueError, match="positive time"):
        Claim(
            claim_id="x", quantity="q", species="mPlasmaVenous", reported=1.0,
            source_location="Table 5", schedule=((0.0, ()),),
        )


def test_the_certificate_records_the_prior_administration() -> None:
    """A reader who re-runs the reported window alone gets a different number, so it is protocol."""
    claim = Claim(
        claim_id="Cmax-250mg-Chung", quantity="plasma Cmax, 250 mg after a 375 mg pre-dose",
        species="mPlasmaVenous", reported=3.9, source_location="Table 5, Chung 250mg, Fitted",
        metric="cmax", schedule=_arm(375, 250), assumption_qualified=True,
    )
    cert = certify_model(
        _MODEL, paper=PaperIdentity(title="Zake2021", doi="10.1371/journal.pone.0249594"),
        engine_pin=engine_pin(), claims=[claim], duration=24.0, steps=1200,
    )
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.REPRODUCED
    protocol = assessment.protocol or ""
    assert "preceded by 12.0 at" in protocol and "292.45" in protocol
    # The claim's own dose is the last segment's, and it is the one reported as the run's override.
    assert "194.96" in protocol


def test_both_engines_walk_the_same_segments() -> None:
    """Corroborating the unscheduled model would report agreement about a run nobody made."""
    pytest.importorskip("roadrunner", reason="the optional 'corroborate' extra")
    from reprolith import corroborate_curve

    result = corroborate_curve(
        _MODEL, "mPlasmaVenous", duration=24.0, steps=480, schedule=_arm(375, 250)
    )
    assert result.stable
    assert result.distance_bound() <= 1e-3


def test_a_scheduled_step_is_not_exported_as_a_plain_run() -> None:
    """The writer would otherwise ship the defect the readers exist to catch.

    A uniform time course cannot say "start from where another run ended", and written as one the
    document would run the reported window alone — a neighbouring arm, producing a plausible
    number and flagging nothing. Listed as unexpressed, never dropped and never guessed at.
    """
    from reprolith import EnginePin, ModelArtifact, ModelOrigin, RecipeStep, ReconstructionBundle
    from reprolith.export import build_bundle_sedml

    scheduled = RecipeStep(
        claim_id="Cmax-250mg-Chung", protocol="Table 5", output="[mPlasmaVenous]",
        time_span="0-24.0", steps=1200, metric="cmax", schedule=_arm(375, 250),
    )
    # Beside an ordinary step, because a bundle of *only* unexpressible steps is refused outright
    # — a document describing no run — and what is being checked here is the mixture a real
    # bundle has: some claims written, the rest named.
    plain = RecipeStep(
        claim_id="Cmax-500mg", protocol="Table 6", output="[mPlasmaVenous]",
        time_span="0-24.0", steps=480, metric="cmax",
    )
    bundle = ReconstructionBundle(
        entry="BIOMD0000001028",
        model=ModelArtifact(filename="m.xml", detected_format="sbml", validates=True),
        origin=ModelOrigin.AUTHOR_SUPPLIED,
        engine_pin=EnginePin(engine="copasi", version="4.46.300", algorithm="deterministic-lsoda"),
        recipe=(plain, scheduled),
    )
    exported = build_bundle_sedml(bundle, _MODEL)
    assert exported.expressed == ("Cmax-500mg",)
    (reason,) = exported.unexpressed
    assert "prior administration" in reason and "Cmax-250mg-Chung" in reason


def test_a_schedule_is_refused_on_a_model_with_more_than_one_event() -> None:
    """Each segment restarts the clock, so every event fires again in every segment.

    That is exactly what administers the dose — the author's own event, fired again — and it is
    also the limit: a second event would fire again too, at the same offset into every segment,
    which is not what the author wrote. A time-triggered event is indistinguishable from a dose
    here, so this is refused rather than guessed at. The metformin models carry one event, which
    is the dose, which is why the corpus is unaffected.
    """
    from reprolith.sbml import _libsbml

    libsbml = _libsbml()
    document = libsbml.readSBMLFromString(_MODEL)
    model = document.getModel()
    template = model.getEvent(0)
    extra = model.createEvent()
    extra.setId("Something_else")
    extra.setUseValuesFromTriggerTime(True)
    trigger = extra.createTrigger()
    trigger.setInitialValue(True)
    trigger.setPersistent(True)
    trigger.setMath(libsbml.parseL3Formula("time > 6"))
    assignment = extra.createEventAssignment()
    assignment.setVariable(template.getEventAssignment(0).getVariable())
    assignment.setMath(template.getEventAssignment(0).getMath().deepCopy())
    two_events = libsbml.writeSBMLToString(document)

    with pytest.raises(ValueError, match="fires again in every segment"):
        _run_schedule(two_events, "mPlasmaVenous", schedule=_arm(375, 250), steps=240)

    # A single-segment schedule is an ordinary run and is not refused: nothing re-fires.
    _run_schedule(two_events, "mPlasmaVenous", schedule=((24.0, ()),), steps=240)


def test_each_engine_reads_its_own_end_state() -> None:
    """A corroboration that shares half its arithmetic with the thing it corroborates is not one.

    The fast path reads a whole segment's end state from one simulation, and its first version
    defaulted to COPASI's reader for both engines — which would have made the "libRoadRunner" run
    half COPASI while still reporting the two as independent.
    """
    pytest.importorskip("roadrunner", reason="the optional 'corroborate' extra")
    from reprolith.engine import final_state, final_state_with_roadrunner

    names = ("mPlasmaVenous", "mStomachLumen", "mLiver")
    copasi = final_state(_MODEL, names, duration=12.0, steps=240)
    roadrunner = final_state_with_roadrunner(_MODEL, names, duration=12.0, steps=240)
    assert set(copasi) == set(roadrunner) == set(names)
    # Independent implementations, so they agree closely without being the same code — to about
    # 1e-6 here. The bound is the one the corroboration criterion itself uses for "these two
    # engines agree", rather than a number fitted to this machine.
    for name in names:
        assert roadrunner[name] == pytest.approx(copasi[name], rel=1e-3), name


def test_the_bulk_end_state_agrees_with_reading_one_species_at_a_time() -> None:
    """The optimisation must not change the answer, only the number of simulations.

    Not exactly, and the reason is documented in `simulate`: COPASI is not bit-identical across
    repeated calls in one process. These are two separate runs of the same model, so they differ
    by the engine's own last-place noise.

    Compared against each species' **own scale** — the largest value it reaches over the run — and
    not against its end value, which is the mistake two rounds of loosening a relative tolerance
    were papering over. `mStomachLumen` starts near 390 and has decayed to 0.053 by twelve hours,
    so an absolute difference of 1e-6 is 2e-5 *relative to what is left*: the denominator is
    vanishing, not the agreement failing. That is the same reasoning `judge_scalar` already
    applies through `zero_scale` — a value with no magnitude has nothing for a relative tolerance
    to mean anything against — arriving here by a different route.

    What this must catch is a bulk read that returns the wrong column or the wrong row, which is
    not a near miss on any scale.
    """
    from reprolith.engine import final_state, simulate

    names = ("mPlasmaVenous", "mStomachLumen", "mLiver")
    bulk = final_state(_MODEL, names, duration=12.0, steps=240)
    for name in names:
        series = simulate(_MODEL, name, duration=12.0, steps=240)[1]
        scale = max(abs(value) for value in series)
        assert abs(bulk[name] - series[-1]) <= 1e-5 * scale, (
            name, bulk[name], series[-1], scale
        )


def test_the_auc_guard_measures_the_scheduled_run_not_the_default_one() -> None:
    """Checking the unscheduled model would report a different integral's convergence.

    The same "checked the wrong run" shape the cross-engine path had, one function over: for a
    scheduled claim `model` is the *unmodified* SBML, because the doses live in the segments.
    """
    from reprolith.certify import _auc_is_established

    scheduled, _ = _auc_is_established(
        _MODEL, "mPlasmaVenous", duration=24.0, steps=240, within=0.05, schedule=_arm(375, 250)
    )
    assert scheduled  # a smooth oral profile converges either way; what matters is which ran

    # The two runs are genuinely different, so a guard reading the wrong one is measurable.
    from reprolith.certify import _metric, _run_schedule

    times, values = _run_schedule(_MODEL, "mPlasmaVenous", schedule=_arm(375, 250), steps=240)
    plain_times, plain_values = simulate(_MODEL, "mPlasmaVenous", duration=24.0, steps=240)
    assert _metric(times, values, "auc") != pytest.approx(
        _metric(plain_times, plain_values, "auc"), rel=0.05
    )
