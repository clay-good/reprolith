"""The first published figure in this corpus: read off the paper's picture, and judged.

Until this file every figure claim in the repository was judged against a series generated from a
known function, because no reading of a real figure existed (`tests/test_digitized_figure_end_to_end.py`
says so in its first paragraph). Figure 5 of Zake et al. 2021 is now read: the paper's own model
simulations of metformin in ten human tissues after single oral doses of 500, 1000 and 1500 mg,
thirty curves, in `datasets/figures/Zake2021_figure5/`.

The reading is a curator's act and is held to two things that do not depend on it:

* **The paper's own printed numbers.** Table 6 prints the peak of every one of those curves. A
  reading whose peaks disagree with the table it was published beside is mis-read, whatever the
  model then does with it — and this is checked without running anything.
* **The image it came from.** `scripts/digitize_figure_panels.py` regenerates every reading from
  the committed image, so a reading cannot drift from the picture it claims to have been read off.

Then the deposited model is judged against it, which is the point: thirty curves, each a whole time
course rather than one number, from a figure rather than a table.
"""

from __future__ import annotations

import importlib
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from reprolith import (
    CurveClaim,
    PaperIdentity,
    ReferenceKind,
    Verdict,
    curve_reference,
    engine_pin,
    interpolation_cost,
    read_digitized_figure,
    window_faults,
)

_REPO = Path(__file__).resolve().parents[1]
_FIGURE = _REPO / "datasets" / "figures" / "Zake2021_figure5"
_MANIFEST = json.loads((_FIGURE / "manifest.json").read_text(encoding="utf-8"))
_ENTRY = json.loads((_REPO / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8"))[
    "entries"
]["BIOMD0000001028"]
_MODEL = _REPO / "datasets" / _ENTRY["model_file"]

#: The model's dose input for each arm: the free base each salt dose is, which is the recorded
#: `dose-salt-form` assumption of this entry. 500 mg is the model's own default.
_DOSE_INPUT = {"500mg": None, "1000mg": 779.9, "1500mg": 1169.79}


def _missing(*modules: str) -> bool:
    """Whether any of ``modules`` cannot be imported here, as in CI's job without the extras."""
    for module in modules:
        try:
            importlib.import_module(module)
        except ImportError:
            return True
    return False


_needs_engine = pytest.mark.skipif(
    _missing("COPASI", "libsbml"),
    reason="the optional 'engine' extra (python-copasi, python-libsbml) is not installed",
)


def _panels():
    for panel in _MANIFEST["panels"]:
        text = (_FIGURE / panel["reading"]).read_text(encoding="utf-8")
        yield panel, read_digitized_figure(text)


def _window(series) -> float:
    """The whole hours every curve of a panel was read over: the run it can be judged on."""
    return float(math.floor(min(s.span[1] for s in series)))


def _table_cmax(species: str, dose: str) -> float:
    """The peak Table 6 prints for one tissue and dose, as this entry's claims already carry it."""
    wanted = _DOSE_INPUT[dose]
    for claim in _ENTRY["claims"]:
        overrides = claim.get("parameter_overrides", {})
        if (
            claim["species"] == species and claim["metric"] == "cmax" and "schedule" not in claim
            and overrides.get("Metformin_Dose_in_Lumen_in_mg") == wanted
        ):
            return float(claim["reported"])
    raise LookupError(f"no single-dose Table 6 Cmax for {species} at {dose}")


def test_every_reading_is_a_reading_the_intake_accepts() -> None:
    """Ten panels, three curves each, every one inside its axes and covering its judged window."""
    count = 0
    for panel, series in _panels():
        assert [s.claim_id for s in series] == [s["claim"] for s in panel["series"]]
        assert not window_faults(series, [(0.0, _window(series))])
        for reading in series:
            assert reading.points[0][0] == 0.0  # the common origin, at the tick it is drawn from
            assert len(reading.points) > 200
            count += 1
    assert count == 30


def test_the_readings_agree_with_the_peaks_the_paper_prints() -> None:
    """The reading checked against the paper's own table, with no model involved.

    Table 6 prints each curve's peak to one decimal place, and every read peak is within 2.2% of
    it (0.7% on average). That is the evidence the digitizer read the picture rather than produced
    something plausible: a mis-calibrated axis is off by a constant factor on every peak, and a
    line read in the wrong colour is off by the gap between two doses — 40% or more.
    """
    misses = []
    for panel, series in _panels():
        for reading, arm in zip(series, panel["series"]):
            peak = max(y for _, y in reading.points)
            printed = _table_cmax(panel["species"], arm["dose"])
            misses.append(abs(peak - printed) / printed)
    assert len(misses) == 30
    assert max(misses) < 0.03
    assert sum(misses) / len(misses) < 0.01


def test_what_each_reading_costs_is_measured_and_inside_the_budget() -> None:
    """The reading's own straight lines spend at most about a third of the figure band.

    The worst is the 500 mg plasma curve at 0.59 h, on the opening rise, where the red line is
    under the two drawn after it for a stretch and is interpolated across; it is reported, not
    hidden, and it is still well inside the budget it is judged in.
    """
    for _, series in _panels():
        for reading in series:
            cost = interpolation_cost(reading, window=(0.0, _window(series)))
            assert cost["measurable"]
            assert cost["budget_share"] < 0.5, (reading.claim_id, cost["budget_share"])


@pytest.mark.skipif(
    _missing("PIL", "numpy"),
    reason="the digitizer needs Pillow and numpy, which the package does not depend on",
)
def test_the_committed_readings_are_what_the_image_gives(tmp_path: Path) -> None:
    """Re-reading the committed image reproduces every committed reading exactly."""
    copy = tmp_path / "figure"
    copy.mkdir()
    (copy / "manifest.json").write_bytes((_FIGURE / "manifest.json").read_bytes())
    image = _MANIFEST["image"]
    (copy / image).write_bytes((_FIGURE / image).read_bytes())
    subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "digitize_figure_panels.py"),
         str(copy / "manifest.json")],
        check=True, capture_output=True,
    )
    for panel in _MANIFEST["panels"]:
        committed = json.loads((_FIGURE / panel["reading"]).read_text(encoding="utf-8"))
        regenerated = json.loads((copy / panel["reading"]).read_text(encoding="utf-8"))
        assert regenerated == committed, panel["reading"]


def _claims(*, dose_of=None, clock: float = 1.0) -> list[CurveClaim]:
    """Every curve as a claim on the deposited model, judged over its panel's covered window.

    ``dose_of`` runs every curve at another arm's dose; ``clock`` reads the figure's hours as that
    many model time units. Both exist to show the verdicts are not vacuous.
    """
    claims = []
    for panel, series in _panels():
        duration = _window(series)
        steps = int(duration * 20)
        for reading, arm in zip(series, panel["series"]):
            dose = _DOSE_INPUT[dose_of or arm["dose"]]
            claims.append(CurveClaim(
                claim_id=reading.claim_id,
                quantity=reading.curve,
                species=panel["species"],
                reference=curve_reference(reading, duration=duration, steps=steps),
                source_location=reading.source_line(window=(0.0, duration)),
                duration=duration * clock,
                steps=steps,
                reference_kind=ReferenceKind.DIGITIZED_FIGURE,
                digitizer=reading.digitizer,
                parameter_overrides=(
                    () if dose is None else (("Metformin_Dose_in_Lumen_in_mg", dose),)
                ),
                assumption_qualified=True,
            ))
    return claims


def _certify(claims):
    from reprolith import certify_curves

    return certify_curves(
        _MODEL.read_text(encoding="utf-8"),
        paper=PaperIdentity(title=_ENTRY["paper"]["title"], doi=_ENTRY["paper"]["doi"]),
        engine_pin=engine_pin(),
        claims=claims,
    )


@_needs_engine
def test_the_deposited_model_reproduces_every_curve_of_the_figure() -> None:
    """Thirty whole time courses, each within the figure band; most within a tenth of it."""
    certificate = _certify(_claims())
    assert len(certificate.assessments) == 30
    for assessment in certificate.assessments:
        assert assessment.verdict is Verdict.REPRODUCED, assessment.claim_id
        assert assessment.reference_kind == ReferenceKind.DIGITIZED_FIGURE.value
        assert "digitized from the figure with scripts/digitize_figure_panels.py" in (
            assessment.source_location
        )


@_needs_engine
def test_the_verdicts_are_not_vacuous() -> None:
    """The same readings fail when the run is not the one the figure plots.

    Two wrong runs, each a mistake a reproducer could actually make: every curve run at the
    1500 mg arm, and the model's clock read as it declares it — one hundred hours to the unit —
    so the figure's thirty hours are 0.3 of a model unit. Neither passes a single curve whose run
    it changes, which is what makes the thirty passes above evidence and not a band too wide to
    miss.
    """
    wrong_dose = _certify(_claims(dose_of="1500mg"))
    for assessment in wrong_dose.assessments:
        if "1500mg" in assessment.claim_id:
            assert assessment.verdict is Verdict.REPRODUCED
        else:
            assert assessment.verdict is not Verdict.REPRODUCED, assessment.claim_id

    declared_clock = _certify(_claims(clock=0.01))
    for assessment in declared_clock.assessments:
        assert assessment.verdict is Verdict.FAILED, assessment.claim_id


def test_the_published_certificate_carries_every_curve_read() -> None:
    """The thirty readings are claims on the entry's certificate, each as a figure reading.

    Read from the committed certificate, so it runs where the engine is not installed: a figure
    claim dropped from the dataset, or a certificate regenerated without them, shows up here rather
    than as a quieter headline.
    """
    read = {s["claim"] for panel in _MANIFEST["panels"] for s in panel["series"]}
    stated = {record["claim_id"] for record in _ENTRY["figure_claims"]}
    assert stated == read

    certificate = json.loads(
        (_REPO / "datasets" / "milestone" / "certificates" / "BIOMD0000001028.json").read_text(
            encoding="utf-8"
        )
    )
    published = {
        a["claim_id"]: a for a in certificate["assessments"] if a["claim_id"] in read
    }
    assert set(published) == read
    for assessment in published.values():
        assert assessment["reference_kind"] == ReferenceKind.DIGITIZED_FIGURE.value
        assert assessment["verdict"] == Verdict.REPRODUCED.value
        assert "digitized from the figure with" in assessment["source_location"]
