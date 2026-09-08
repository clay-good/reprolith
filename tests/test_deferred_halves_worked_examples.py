"""The two deferred halves' first published artifacts, held to what they say.

`simulate_population` and `refit_parameters` were both built, both tested, and neither had ever
produced anything a reader could look at: `docs/population-and-estimation.md` had to say that no row
in the registry came from either path, and the demonstration lived in a test. It lives in a
committed certificate now, and this is the gate on it — the same shape the other worked examples
carry, so a hand-edited verdict cannot sit in a published render.

Nothing here re-runs the simulator or the optimizer: the committed certificate is checked against
the committed *reference* it was judged against, and the render is checked against the certificate.
Re-fitting in CI would be a second, slower copy of `test_estimation_refit.py`, and would make a
platform's last-place arithmetic a failure of a published artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import RunMetadata, certificate_from_content, render_human

_DATASETS = Path(__file__).parent.parent / "datasets"
_POPULATION = _DATASETS / "population" / "worked_example"
_ESTIMATION = _DATASETS / "estimation" / "worked_example"
#: The stamp `scripts/render_worked_examples.py` renders under. Run metadata sits outside the
#: content hash and `render_human` prints none of it, so this only has to match the script's.
_RUN = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1")


def _certificate(directory: Path):
    return certificate_from_content(
        json.loads((directory / "certificate.json").read_text(encoding="utf-8"))
    )


@pytest.mark.parametrize("directory", [_POPULATION, _ESTIMATION])
def test_the_render_is_the_rendering_of_the_committed_certificate(directory: Path) -> None:
    """Byte for byte, so an edited verdict in the text is a failure rather than a publication."""
    rendered = render_human(_certificate(directory), _RUN) + "\n"
    assert rendered == (directory / "certificate.txt").read_text(encoding="utf-8")


def test_the_population_certificate_is_judged_against_the_committed_reference() -> None:
    """The bands it reproduces are the ones in `reference.json`, not ones it computed itself."""
    reference = json.loads((_POPULATION / "reference.json").read_text(encoding="utf-8"))
    content = json.loads((_POPULATION / "certificate.json").read_text(encoding="utf-8"))
    assert set(reference["bands"]) == {"5.0", "50.0", "95.0"}
    assert len(reference["times"]) == 13  # duration 12, 12 steps
    assert reference["between_subject_cv_of_peak"] == 0.3
    assessment = content["assessments"][0]
    assert assessment["method"] == "distribution-band-distance"
    assert assessment["verdict"] == "reproduced"
    # At *simulation* level, and deliberately: the two levels this engine distinguishes are running
    # the described model and re-fitting it from raw data, and a population is the first of those
    # run many times. What makes it a different kind of result is the comparison and the
    # assumption, both of which are on the certificate.
    assert assessment["level"] == "simulation"
    # The reference is mathematics standing in for a figure, and the claim line says so rather than
    # letting a reader take it for a paper's published envelope.
    assert "standing in for a published figure" in assessment["source_location"]


def test_the_population_certificate_carries_both_halves_of_a_population_claim() -> None:
    """An envelope and a variability metric, and each protocol line is about its own claim.

    The band's sampling error is the envelope's precision and not the CV's; a spread claim handed
    the full envelope line would state the precision of a quantity it is not about.
    """
    content = json.loads((_POPULATION / "certificate.json").read_text(encoding="utf-8"))
    by_id = {a["claim_id"]: a for a in content["assessments"]}
    assert set(by_id) == {"population-envelope", "between-subject-cv"}
    assert by_id["between-subject-cv"]["method"] == "scalar-relative-error"
    assert "jackknife standard error" in by_id["between-subject-cv"]["protocol"]
    assert "of the band at" not in by_id["between-subject-cv"]["protocol"]
    assert "of the band at" in by_id["population-envelope"]["protocol"]
    # 1,500 subjects, because at 500 the spread claim would be abstained on rather than judged.
    assert "1500 subjects" in by_id["between-subject-cv"]["protocol"]


def test_the_population_verdict_is_qualified_and_names_what_qualifies_it() -> None:
    """A clean per-claim `reproduced` and a qualified certificate is the invariant, not a shortfall:
    the envelope rests on a variability model and a sampling Reprolith chose."""
    content = json.loads((_POPULATION / "certificate.json").read_text(encoding="utf-8"))
    assert content["overall"] == "partially-reproduced"
    assumptions = content["assumptions"]
    assert len(assumptions) == 2  # one per claim, each naming the sampling it rests on
    for assumption in assumptions:
        assert assumption["load_bearing"] is True
        # The sampling is this engine's, not the paper's: no wording closes it.
        assert assumption["author_can_close"] is False
        assert "1500 subjects, seed 20260901" in assumption["chosen"]


def test_the_estimation_certificate_recovers_the_value_its_data_came_from() -> None:
    reference = json.loads((_ESTIMATION / "reference.json").read_text(encoding="utf-8"))
    content = json.loads((_ESTIMATION / "certificate.json").read_text(encoding="utf-8"))
    assert reference["true_k"] == 0.2
    assert reference["start_k"] == 0.05  # a factor of four away, so the fit had to travel
    assessment = content["assessments"][0]
    assert assessment["verdict"] == "reproduced"
    assert assessment["level"] == "estimation"
    # All four things a re-fit is sensitive to, on the line a reader would repeat it from.
    for part in ("least squares", "Nelder-Mead", "k=0.05", "observations"):
        assert part in assessment["protocol"]


def test_the_estimation_certificate_says_what_an_estimation_verdict_does_not_include() -> None:
    """Recovering a paper's parameter is not the same as reproducing its simulated results.

    Read off the render rather than out of `gap_report`, because that is where it is: the line is
    derived from the claim's *level* when the certificate is rendered, not stored as a gap. A
    reader meets it under "WHAT WAS MISSING", which is the surface this is about.
    """
    text = (_ESTIMATION / "certificate.txt").read_text(encoding="utf-8")
    missing = text.split("WHAT WAS MISSING", 1)[1]
    assert "reproduced at estimation level (parameters re-fit from data)" in missing
    assert "simulation reproduction of this claim was not demonstrated" in missing
