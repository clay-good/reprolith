"""A model whose quantities have positions but no meanings, and the entry it blocks.

Every other check in this family is about a file a reader cannot *use*: an element with no id, a
reaction with no rate. This one is about a file that works perfectly. BioModels BIOMD0000000608 —
Palsson et al. 2013's fully-integrated immune response model — loads under this repository's own
pin, integrates in under a second, and returns a finite trajectory for each of its **52 species,
every one of them named `x_1` through `x_52`**, with no `name` that differs from the id, no SBO
term and no annotation anywhere in the document.

That is why the entry is blocked, and the fact was not available before this check. Its paper's
figures are 600-pixel BMC images with four closed plotting boxes and up to nine separable hues —
readable, by this repository's own measurements (`datasets/manuscripts/figure_survey.json`) — and
its model runs. What is missing is not the picture and not the engine: there is no output to point
a claim at. "Needs figure digitization" was the whole account of this entry, and it was wrong.

The rule is narrow because the cost of being wrong is sending an author to repair a correct file,
so it is swept over every model committed here: 277 species across twenty-one models, one reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import claims_template, species_without_stated_meanings

_FIXTURES = Path(__file__).parent / "fixtures"
_DATASETS = Path(__file__).parent.parent / "datasets"

#: Three species in the shape the real deposit uses — a slot number for an id and the same string
#: repeated as a name, which is what BioModels' own SBML writer emits for a model whose source
#: named nothing — plus one that says what it is.
_ANONYMOUS = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
    <listOfSpecies>
      <species id="x_1" name="x_1" compartment="c" initialConcentration="10"/>
      <species id="x_2" name="x_2" compartment="c" initialConcentration="0"/>
      <species id="x_3" compartment="c" initialConcentration="0"/>
      <species id="Glucose" compartment="c" initialConcentration="5"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.5"/></listOfParameters>
    <listOfReactions>
      <reaction id="r1" reversible="false">
        <listOfReactants><speciesReference species="x_1"/></listOfReactants>
        <listOfProducts><speciesReference species="x_2"/></listOfProducts>
        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><times/><ci>k</ci><ci>x_1</ci></apply></math></kineticLaw>
      </reaction>
      <reaction id="r2" reversible="false">
        <listOfReactants><speciesReference species="x_2"/></listOfReactants>
        <listOfProducts><speciesReference species="x_3"/></listOfProducts>
        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><times/><ci>k</ci><ci>x_2</ci></apply></math></kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""


def test_a_slot_number_with_no_meaning_beside_it_is_reported() -> None:
    """All three shapes of saying nothing: the name repeating the id, and the name absent."""
    assert species_without_stated_meanings(_ANONYMOUS) == ("x_1", "x_2", "x_3")


def test_anything_the_file_says_about_a_quantity_takes_it_off_the_list() -> None:
    """Three ways to answer the check, each of which is the author stating what they mean.

    Each is tested on its own rather than all at once, because a rule that needed all three would
    report a model that names its species perfectly well in the author's own words.
    """
    named = _ANONYMOUS.replace('id="x_1" name="x_1"', 'id="x_1" name="naive CD4 T cells"')
    assert species_without_stated_meanings(named) == ("x_2", "x_3")

    with_sbo = _ANONYMOUS.replace('id="x_2" name="x_2"', 'id="x_2" name="x_2" sboTerm="SBO:0000247"')
    assert species_without_stated_meanings(with_sbo) == ("x_1", "x_3")

    annotated = _ANONYMOUS.replace(
        '<species id="x_3" compartment="c" initialConcentration="0"/>',
        '<species id="x_3" compartment="c" initialConcentration="0">'
        '<annotation><whatever xmlns="http://example.invalid/ns"/></annotation></species>',
    )
    assert species_without_stated_meanings(annotated) == ("x_1", "x_2")


def test_an_id_that_reads_as_a_word_is_never_reported_however_terse() -> None:
    """The false positive that would matter, since real models name genes and proteins tersely.

    `IL6` is why the rule allows one letter and not two. An interleukin is a quantity an immune
    model names exactly that way, and the first version of this check — `[A-Za-z]{1,2}` — reported
    it, on the very paper the check was written for.
    """
    for identifier in ("Glucose", "ALDOB", "C1q", "pIRS1", "x", "APAP_gut", "S1P", "IL6", "IL10"):
        model = _ANONYMOUS.replace('id="x_1" name="x_1"', f'id="{identifier}" name="{identifier}"')
        assert identifier not in species_without_stated_meanings(model), identifier


def test_every_model_this_repository_ships_states_what_its_species_are() -> None:
    """The sweep, for the same reason the rate-law check has one: a check whose false positive
    sends an author to repair a correct file has to be tried against the correct files first.

    One species is reported, and it is reported rightly: `X1` in Sluka et al. 2016's metabolism
    module, a boundary species fixed at zero that the file never explains. One of seven is a very
    different report from fifty-two of fifty-two, and the count is what tells them apart."""
    models = sorted(
        path for directory in (_FIXTURES, _DATASETS) for path in directory.rglob("*.xml")
    )
    assert len(models) >= 15, "the sweep must actually reach this repository's models"
    reported: dict[str, tuple[str, ...]] = {}
    for path in models:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "<sbml" not in text:
            continue
        found = species_without_stated_meanings(text)
        if found:
            reported[path.name] = found
    assert reported == {"Sluka2016_APAP_metabolism.xml": ("X1",)}, reported


def test_the_claims_template_says_so_where_the_author_will_read_it() -> None:
    """The surface parity that matters: an author writing claims by hand starts here, not at
    `archive-check`, and `readable_outputs` would otherwise hand them rows reading `x_1` with
    nothing said about why that is a problem rather than a style."""
    template = claims_template(_ANONYMOUS)
    (note,) = [n for n in template["notes"] if "identified only by position" in n]
    assert "x_1, x_2, x_3" in note
    assert "3 of this model's species" in note
    # And the outputs it is about are still listed, because the author has to see both.
    assert {output["id"] for output in template["readable_outputs"]} >= {"x_1", "x_2", "x_3"}
    # A model that says what it means gets no such note at all.
    named = _ANONYMOUS.replace('name="x_1"', 'name="a"').replace(
        'name="x_2"', 'name="b"'
    ).replace('<species id="x_3" ', '<species name="c" id="x_3" ')
    assert not [n for n in claims_template(named)["notes"] if "identified only by position" in n]


def test_no_engine_says_it_and_that_is_the_point() -> None:
    """The check's whole justification: this file is not broken, it is unusable.

    Both engines integrate it to completion and return one curve per anonymous species. If either
    of them ever starts complaining, the report is telling authors something about reproducers
    that is no longer true."""
    from reprolith import simulate

    pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
    times, values = simulate(_ANONYMOUS, "x_3", duration=10.0, steps=5)
    assert len(values) == 6 and values[-1] > 0.0
    assert all(value == value for value in values)  # finite throughout: nothing to complain about

    roadrunner = pytest.importorskip(
        "roadrunner", reason="the optional 'corroborate' extra is not installed"
    )
    result = roadrunner.RoadRunner(_ANONYMOUS).simulate(0, 10, 5)
    columns = [name.strip("[]") for name in result.colnames]
    assert {"x_1", "x_2", "x_3"} <= set(columns)
    assert list(result)[-1][columns.index("x_3")] > 0.0


def test_archive_check_reports_it_to_the_author_submitting_the_archive() -> None:
    """The other author-facing surface, so one deposit gets one explanation whichever is reached.

    Below an element with no identifier at all and above a missing rate law: an anonymous element
    makes the two engines disagree about what was shipped, which is worse, and an absent rate law
    is at least visible in the file, which makes this worse than that.
    """
    import io
    import zipfile

    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import archive_report, render_archive_human

    specification = "http://identifiers.org/combine.specifications/"
    sedml = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version4" level="1" version="4">
  <listOfModels>
    <model id="m" language="urn:sedml:language:sbml" source="model.xml"/>
  </listOfModels>
  <listOfSimulations>
    <uniformTimeCourse id="s" initialTime="0" outputStartTime="0" outputEndTime="10"
                       numberOfSteps="5"/>
  </listOfSimulations>
  <listOfTasks><task id="t" modelReference="m" simulationReference="s"/></listOfTasks>
  <listOfDataGenerators/>
  <listOfOutputs/>
</sedML>
"""
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{specification}omex-manifest">
  <content location="./manifest.xml" format="{specification}omex-manifest"/>
  <content location="./model.xml" format="{specification}sbml.level-2.version-4"/>
  <content location="./experiment.sedml" format="{specification}sed-ml" master="true"/>
</omexManifest>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.xml", manifest)
        archive.writestr("model.xml", _ANONYMOUS)
        archive.writestr("experiment.sedml", sedml)
    bytes_ = buffer.getvalue()

    report = archive_report(bytes_)
    assert report["found"]["species_without_stated_meanings"] == ["x_1", "x_2", "x_3"]
    (action,) = [item for item in report["fix_list"] if item["kind"] == "no-meaning"]
    assert "identified only by position" in action["issue"]
    assert "x_1, x_2, x_3" in action["issue"]
    # It says what no engine will say, which is the reason it is a check.
    assert "integrate it to completion" in action["issue"]
    rendered = render_archive_human(bytes_)
    assert "identified only by position" in rendered

    # It shares a tier with a missing rate law, so document order decides between them — and this
    # one comes first, because a model whose quantities have no meanings is not repaired by
    # adding rate laws to it. Both are made to fire, or the ordering is untested.
    rate_less = _ANONYMOUS.replace(
        """        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><times/><ci>k</ci><ci>x_2</ci></apply></math></kineticLaw>
""",
        "",
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.xml", manifest)
        archive.writestr("model.xml", rate_less)
        archive.writestr("experiment.sedml", sedml)
    both = archive_report(buffer.getvalue())
    assert both["found"]["reactions_without_rate_laws"] == ["r2"]
    kinds = [item["kind"] for item in both["fix_list"]]
    assert kinds.index("no-meaning") < kinds.index("rate-law")


def test_the_figure_survey_and_this_check_disagree_about_what_blocks_the_entry() -> None:
    """Two measurements of one blocked entry, which only together say what is in the way.

    The survey says Palsson et al. 2013's figures are large, framed and drawn in up to nine
    separable colours — readable by every property of the image this repository can measure. So a
    reader with only the survey would pick that paper up next and get a long way before finding
    that nothing in the model can be pointed at. The two belong in one place, and this is it.
    """
    survey = json.loads(
        (_DATASETS / "manuscripts" / "figure_survey.json").read_text(encoding="utf-8")
    )
    (palsson,) = [p for p in survey["papers"] if "BIOMD0000000608" in p["entries"]]
    readable = [f for f in palsson["figures"] if f["frame"] and f["colours"] >= 2]
    assert len(readable) >= 3, readable
    assert max(f["colours"] for f in readable) >= 7
    assert palsson["license"] == "cc by"
