"""What the blocked entries' figures are, measured — and the belief it refutes.

"The rest need figure digitization" was the whole account of twenty-four blocked entries, and it
says nothing about which of them is an afternoon's work. Four figures have now been read and three
more were opened and abandoned, so the difference is observable, and
`scripts/survey_published_figures.py` measures it over every figure of every blocked paper it can
fetch.

The belief worth refuting first is that the obstacle is **size**. It is not: this repository has
read ten panels of 280x257 pixels and abandoned one of 234x200. What separates them is whether the
panel is a closed box the trace can locate, how many hues the lines are drawn in, and — the one no
property of the image shows — whether the curve is resolvable in the panel it occupies.

Pure stdlib, so this runs on the dependency-free core gate.
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SURVEY = json.loads(
    (_ROOT / "datasets" / "manuscripts" / "figure_survey.json").read_text(encoding="utf-8")
)
_FIGURES = _ROOT / "datasets" / "figures"


def _measured() -> list[dict]:
    return [figure for paper in _SURVEY["papers"] for figure in paper.get("figures", ())]


def test_the_survey_covers_the_papers_the_blocked_entries_name() -> None:
    """Each paper here holds at least one blocked entry, and the file says which."""
    papers = {paper["pmcid"]: paper for paper in _SURVEY["papers"]}
    assert len(papers) >= 7, sorted(papers)
    for pmcid, paper in papers.items():
        assert pmcid.startswith("PMC"), pmcid
        assert paper["entries"], pmcid
        assert paper["paper"].strip(), pmcid
        # The licence is recorded for every paper, empty when the service states none: what it
        # decides is whether the image file may be re-encoded, not whether it may be read.
        assert isinstance(paper["license"], str), pmcid
    # The entries it accounts for are blocked ones: none of them has a certificate.
    certified = {
        path.stem for path in (_ROOT / "datasets" / "milestone" / "certificates").glob("*.json")
    }
    for paper in papers.values():
        assert not (set(paper["entries"]) & certified), paper["pmcid"]


def test_every_measured_figure_carries_the_three_properties_that_decide_it() -> None:
    measured = _measured()
    assert len(measured) >= 20, f"only {len(measured)} figures measured; the survey is thinning"
    for figure in measured:
        assert figure["width"] > 0 and figure["height"] > 0, figure["file"]
        assert isinstance(figure["frame"], bool), figure["file"]
        assert figure["colours"] >= 0, figure["file"]
        assert figure["pixels_per_panel"] > 0, figure["file"]


def test_size_is_not_what_separates_a_readable_figure_from_an_unreadable_one() -> None:
    """The claim the survey exists to settle, checked against the figure already read.

    Zake et al. 2021's ten panels are 280x257 pixels and every one of them is on a published
    certificate. The survey holds figures whose whole image is larger than that *and* framed *and*
    drawn in two or more separable colours, and every entry they belong to is still blocked — so
    whatever is in the way of those, it is not a publisher serving small files. A reader who
    assumes it is will spend an afternoon on the wrong figure.

    The comparison is image-against-panel, which is as far as the survey can take it: nobody has
    counted these papers' panels, so `pixels_per_panel` is an upper bound on every figure in it
    and a twelve-panel image like Koeller's reads as one big picture here. That is stated in the
    file's own limits rather than papered over, and it is also why a figure measuring as readable
    is a candidate to open and not a promise.
    """
    read = json.loads((_FIGURES / "Zake2021_figure5" / "manifest.json").read_text(encoding="utf-8"))
    panel = read["panels"][0]["crop"]
    area_that_was_read = (panel[2] - panel[0]) * (panel[3] - panel[1])
    assert area_that_was_read < 100_000, area_that_was_read

    candidates = [
        figure for figure in _measured()
        if figure["frame"]
        and figure["colours"] >= 2
        and figure["pixels_per_panel"] > area_that_was_read
    ]
    assert candidates, "a blocked paper with a framed, coloured, larger figure is the whole point"

    # And the file says in its own limits why being a candidate is not the same as being readable.
    assert any("resolvable in the panel" in limit for limit in _SURVEY["limits"])
    assert any("never a certainty" in limit for limit in _SURVEY["limits"])


def test_a_no_derivatives_licence_is_recorded_as_a_constraint_not_a_refusal() -> None:
    """The licence question that was escalated once and should not be again.

    Benson et al. 2014 is CC BY-NC-ND and six of its curves are on a published certificate: the
    figure is redistributed in the publisher's own bytes, which is what that licence permits. So a
    restrictive licence in this file is a constraint on the *file* — do not re-encode it — and the
    limits say so, rather than the survey reading as a list of papers that may not be touched.
    """
    restrictive = [p for p in _SURVEY["papers"] if "-nd" in p["license"].lower()]
    assert restrictive, "the blocked set contains no-derivatives papers; this file should say so"
    (limit,) = [limit for limit in _SURVEY["limits"] if limit.startswith("`license`")]
    assert "rather than whether it can be read" in limit
    assert "un-re-encoded" in limit
    # And the one already read under that licence is committed as the publisher served it.
    read = _FIGURES / "Benson2014_figure5"
    manifest = json.loads((read / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["image"].endswith(".jpg"), manifest["image"]


def test_the_summary_is_the_per_figure_records_added_up() -> None:
    """The conclusion is carried in the file, and it is not allowed to drift from the measurements.

    A derived count that nothing checks is how a survey comes to say something its own rows do
    not, so the three numbers are recomputed here from the rows they summarise.
    """
    measured = _measured()
    framed = [figure for figure in measured if figure["frame"]]
    summary = _SURVEY["summary"]
    assert summary["measured"] == len(measured)
    assert summary["with_closed_frame"] == len(framed)
    assert summary["framed_and_separable_by_colour"] == sum(
        1 for figure in framed if figure["colours"] >= 2
    )
    unreachable = sorted(p["pmcid"] for p in _SURVEY["papers"] if "error" in p)
    assert summary["unreachable"] == unreachable
    assert summary["carried_from_an_earlier_run"] == sorted(
        p["pmcid"] for p in _SURVEY["papers"] if "carried_from" in p
    )
    # A paper that did not answer either contributed nothing — which is what makes the counts a
    # floor — or says in the row itself that its figures are an earlier run's.
    for paper in _SURVEY["papers"]:
        if "error" in paper and paper.get("figures"):
            assert paper["carried_from"].startswith("an earlier run"), paper["pmcid"]
        if "carried_from" in paper:
            assert "error" in paper, paper["pmcid"]


def test_the_file_says_its_own_counts_are_a_floor() -> None:
    """The supplementary endpoint answers differently on every call, which a census cannot ignore.

    Runs minutes apart returned 51 figures, then 44, then nothing at all — every paper an error. A
    committed survey that quietly got emptier is the shape this repository refuses everywhere
    else, so the script refuses to shrink its own output and the file says the counts are a floor.
    """
    assert any("never a census" in limit for limit in _SURVEY["limits"])
    assert any("contributed nothing" in limit for limit in _SURVEY["limits"])


def test_the_notices_cover_this_file_and_say_what_it_does_not_store() -> None:
    """Three of these papers are no-derivatives, so what the survey keeps is an attribution fact.

    It keeps measurements and no image, which is why measuring a CC BY-NC-ND figure needs no
    licence argument at all — and a notices file that did not say so would leave the next reader
    to work that out again, or to assume the images are here.
    """
    notices = (_ROOT / "datasets" / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    (row,) = [line for line in notices.splitlines() if "figure_survey.json" in line]
    assert "no image is stored" in row
    assert "Europe PMC" in row
    # And the survey really does keep no image: every value in it is a number, a string or a list.
    def plain(value: object) -> bool:
        if isinstance(value, dict):
            return all(plain(item) for item in value.values())
        if isinstance(value, list):
            return all(plain(item) for item in value)
        return isinstance(value, (str, int, float, bool)) or value is None

    assert plain(_SURVEY)
    assert all(len(str(figure["file"])) < 200 for figure in _measured())


def test_the_frameless_pair_the_docstring_named_was_right_all_along() -> None:
    """Three readings of one question, and the middle one was this script's own bug.

    The script's docstring named Dwivedi et al. 2014 and Demin et al. 2013 as the pair whose
    figures are drawn with L-shaped axes and so cannot be traced. A first measurement appeared to
    refute it for Dwivedi — five of eight figures framed — and on the strength of that number the
    paper behind four blocked entries was written up as the backlog's best remaining candidate and
    the docstring was "corrected" to match.

    The number was wrong. `_closed_frame` counted inked *rows*, so one axis line drawn three
    pixels thick counted as three, and Dwivedi's Figure 3 — two panels with L-shaped axes, one
    above the other, sharing a y axis — measured as a closed box. Corrected to count *lines*, the
    docstring's original claim stands: one of Dwivedi's six figures holds a box, and it is Figure
    5, the dose-response that is a capability gap rather than a reading.

    So this test pins the thing that was twice got wrong by prose: both papers are frameless in
    the sense that matters, and the grouping that decides it is held by
    `tests/test_frame_detection_parity.py` against the digitizer's own implementation.
    """
    papers = {paper["pmcid"]: paper for paper in _SURVEY["papers"]}
    for pmcid in ("PMC4026633", "PMC3910013"):
        paper = papers[pmcid]
        assert "carried_from" not in paper, (
            f"{pmcid} must be measured by the current build for this test to mean anything"
        )
        framed = [figure for figure in paper["figures"] if figure["frame"]]
        assert len(framed) <= 1, (pmcid, [f["file"] for f in framed])

    # And the script no longer carries the conclusion the bug produced.
    script = (_ROOT / "scripts" / "survey_published_figures.py").read_text(encoding="utf-8")
    assert "Dwivedi's do not" not in script


def test_the_counts_say_how_much_of_themselves_this_build_measured() -> None:
    """A headline that silently spans two builds is the quiet kind of wrong, and it happened.

    When the frame test was corrected, the run that applied it could re-reach only two of the
    seven papers; the other five kept figures measured by the build with the bug in it. The
    per-paper `carried_from` said so, but the summary counts added old and new together without a
    word. Now they say how many of the counted figures this build actually measured.
    """
    summary = _SURVEY["summary"]
    fresh = [
        figure for paper in _SURVEY["papers"] if "carried_from" not in paper
        for figure in paper.get("figures", ())
    ]
    assert summary["measured_in_this_run"] == len(fresh)
    assert summary["measured_in_this_run"] <= summary["measured"]
    carried = summary["measured"] - summary["measured_in_this_run"]
    assert (carried > 0) == bool(summary["carried_from_an_earlier_run"])
    assert any("span builds" in limit for limit in _SURVEY["limits"])
