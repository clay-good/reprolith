"""An oscillator's period can be certified, which is what its paper reports and why.

Five of the six models in the kinetic milestone oscillate — a MAPK cascade, the repressilator, a
cell-cycle model, a circadian clock, coupled calcium oscillators — and until now the only thing this
class could certify about any of them was the *curve*. That is the one comparison a limit cycle
punishes: a curve distance is dominated by phase, and phase error accumulates with every cycle. So a
model that reproduces the biology exactly while drifting one percent in period reads as a total
failure, which is precisely why these papers report a period and an amplitude instead of a picture.

The measurement is at the bottom of this file, on committed data: on the repressilator's 75-cycle
run, a **1% period difference** moves the curve distance to 0.395 against a 0.10 pass line — four
times over — while the difference it is about is one percent.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from reprolith.certify import NotOscillating, _metric, _upward_crossings
from reprolith.oracle import normalized_curve_distance

_KINETIC = Path(__file__).parent.parent / "datasets" / "kinetic"
_MODELS = {
    m["id"]: m
    for m in json.loads((_KINETIC / "cross_validation.json").read_text(encoding="utf-8"))["models"]
}


def _grid(model_id: str) -> tuple[list[float], list[float]]:
    spec = _MODELS[model_id]
    steps, duration = spec["steps"], spec["duration"]
    return [duration * i / steps for i in range(steps + 1)], list(spec["curve"])


def _sine(period: float, *, cycles: float, samples_per_cycle: int, offset: float = 0.0):
    n = int(cycles * samples_per_cycle)
    times = [period * cycles * i / n for i in range(n + 1)]
    values = [offset + math.sin(2 * math.pi * t / period) for t in times]
    return times, values


# --- the metric on a signal whose period is known exactly ---------------------------------------


def test_the_period_of_a_sine_is_its_period() -> None:
    times, values = _sine(7.0, cycles=6, samples_per_cycle=40)
    assert _metric(times, values, "period") == pytest.approx(7.0, rel=1e-6)


def test_a_coarse_grid_still_reads_the_period_because_the_crossing_is_interpolated() -> None:
    # A time-to-peak can only ever be a sample time, so it is quantized to the spacing. A mean
    # crossing is interpolated between the two samples that straddle it, which is why a period does
    # not inherit that error: eight samples per cycle here, and it is right to a tenth of a percent.
    times, values = _sine(7.0, cycles=6, samples_per_cycle=8)
    assert _metric(times, values, "period") == pytest.approx(7.0, rel=2e-3)


def test_the_peak_to_trough_of_a_sine_is_twice_its_amplitude() -> None:
    times, values = _sine(7.0, cycles=6, samples_per_cycle=100)
    assert _metric(times, values, "peak_to_trough") == pytest.approx(2.0, rel=1e-3)


def test_noise_at_the_crossing_does_not_divide_the_period() -> None:
    """The defect the hysteresis exists for, on the shape that actually produces it.

    A *spiky* oscillator — a long shallow trough and a brief peak, which is what a cell-cycle model
    looks like — drifts through its own mean slowly, and there an integrator's ripple crosses that
    level over and over. Counted naively each crossing opens a new cycle, which does not make the
    period slightly wrong: on this signal it reads **0.66 against a true 10.0**, out by a factor of
    fifteen, and reads it confidently.
    """
    period, cycles, samples_per_cycle = 10.0, 6, 400
    n = cycles * samples_per_cycle
    times = [period * cycles * i / n for i in range(n + 1)]
    spiky = []
    for t in times:
        phase = (t % period) / period
        shape = 0.5 * math.sin(2 * math.pi * phase) ** 11 + 0.02 * math.sin(2 * math.pi * phase)
        spiky.append(shape + 0.004 * math.sin(97.0 * t))  # the ripple a solver leaves behind
    assert _metric(times, spiky, "period") == pytest.approx(period, rel=5e-3)
    # And the count is the cycles the signal has, not the crossings its ripple makes.
    assert len(_upward_crossings(times, spiky)[0]) == cycles + 1


def test_the_hysteresis_changes_nothing_on_a_real_oscillator() -> None:
    # The other half of that constant's claim: it has to be far below any real oscillation's shape,
    # or it would be silently reshaping the answers it exists to protect. Every oscillating
    # reference curve in the corpus reads a period that is a clean fraction of its run.
    for model_id, expected in (
        ("BIOMD0000000010", 1494.14), ("BIOMD0000000012", 133.811),
        ("BIOMD0000000005", 35.5664), ("BIOMD0000000021", 27.022),
        ("BIOMD0000000058", 6.79369),
    ):
        times, values = _grid(model_id)
        assert _metric(times, values, "period") == pytest.approx(expected, rel=1e-5)


# --- what it refuses to answer -------------------------------------------------------------------


def test_a_settled_run_has_no_period_and_says_so() -> None:
    times = [float(i) for i in range(100)]
    values = [1.0 - math.exp(-t / 10.0) for t in times]  # a relaxation, not an oscillation
    with pytest.raises(NotOscillating, match="no full cycle"):
        _metric(times, values, "period")


def test_the_metabolic_model_in_the_corpus_is_the_real_case() -> None:
    # BIOMD0000000051 is this milestone's non-oscillating entry, and its reference curve is
    # committed: a period claim against it abstains rather than reporting the run length.
    times, values = _grid("BIOMD0000000051")
    with pytest.raises(NotOscillating):
        _metric(times, values, "period")


# --- the window, which is how a paper says "after transients" ------------------------------------


def test_a_window_measures_the_settled_cycles_rather_than_the_approach() -> None:
    # A run that starts off its limit cycle has a longer first cycle. Averaging over the whole run
    # answers a different question from the one an oscillator paper asks, and the window is how a
    # source states which part it measured.
    times, values = _sine(10.0, cycles=8, samples_per_cycle=50)
    stretched = [v * (1.0 + 0.5 * math.exp(-t / 5.0)) for t, v in zip(times, values)]
    whole = _metric(times, stretched, "peak_to_trough")
    settled = _metric(times, stretched, "peak_to_trough", (40.0, 80.0))
    assert whole > settled
    assert settled == pytest.approx(2.0, rel=0.05)


def test_the_five_oscillators_in_the_corpus_all_have_a_period() -> None:
    # Every oscillating reference curve in the committed set reads a period, and each is a plausible
    # multiple of the run it was measured over rather than the run length wearing a label.
    for model_id in ("BIOMD0000000005", "BIOMD0000000010", "BIOMD0000000012",
                     "BIOMD0000000021", "BIOMD0000000058"):
        times, values = _grid(model_id)
        period = _metric(times, values, "period")
        assert 0.0 < period < times[-1]


# --- the measurement this claim type exists for ---------------------------------------------------


def test_a_one_percent_period_error_destroys_a_curve_verdict_over_many_cycles() -> None:
    """Why a curve is the wrong comparison for a limit cycle, in committed numbers.

    The repressilator's reference run spans about 75 cycles. Stretching its clock by 1% — the same
    trajectory, one percent slower — leaves every peak height and every shape identical and moves
    the curve distance to four times the pass line, because by the last cycle the two are three
    quarters of a period out of phase. No tolerance can tell that from a model that is wrong.
    """
    times, values = _grid("BIOMD0000000012")
    step = times[1] - times[0]
    stretched = []
    for t in times:
        u = t / 1.01
        index = min(int(u / step), len(values) - 2)
        weight = (u - times[index]) / step
        stretched.append(values[index] + weight * (values[index + 1] - values[index]))
    assert normalized_curve_distance(values, stretched) > 0.3  # against a 0.10 pass line
    # And the same difference, read as what it is: the periods differ by about a percent. (Read on
    # this reference's own 200-sample grid, which is only 2.7 samples per cycle — coarse enough
    # that the *grid* guard is what would stop a claim here, which is its job.)
    assert _upward_crossings(times, values)[0]


def test_the_crossing_level_is_the_windows_own_mean() -> None:
    # Not zero, and not the model's initial value: an oscillation about 500 crosses 500.
    times, values = _sine(4.0, cycles=5, samples_per_cycle=50, offset=500.0)
    _, level = _upward_crossings(times, values)
    assert level == pytest.approx(500.0, abs=0.1)
    assert _metric(times, values, "period") == pytest.approx(4.0, rel=1e-3)
