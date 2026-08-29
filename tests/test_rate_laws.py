"""A reaction that states no rate, and the two engines that disagree about what it means.

The check exists because of a real deposition. BioModels MODEL1711210003 — the estradiol
PBPK/genome-scale model, the one remaining open-access paper in this repository's set that prints
a results table — ships 118 reactions and rate laws for none of them: 114 carry
``<kineticLaw><math/></kineticLaw>`` and 4 carry no ``kineticLaw`` at all. libSBML reports the 114
as "container must not be empty" and hands the model back anyway.

What makes it worth a check rather than an engine's error message is measured in the engine tests
below. No engine says a reaction states no rate; each fails its own way:

* **COPASI** imports either shape, starts the run, and abandons it at t=1.0 of 4.0 — 2 of 5
  samples, all finite. Reprolith's completion check is what turns that into an error.
* **libRoadRunner** refuses an empty ``math`` with an LLVM message about AST nodes, and integrates
  an *absent* ``kineticLaw`` to completion with that reaction's rate taken as zero and nothing
  printed.

The wording in the earlier version of this file said COPASI "refuses the file". It does not, and
the measurement that said so was an artifact of the harness: ``importSBML`` takes a *filename*, so
handing it SBML text makes it try to open a file named by the whole document and fail. The engine
path here goes through ``reprolith.simulate``, which uses ``importSBMLFromString`` as the rest of
the repository does — a test that asserts an engine refuses something has to be run through the
loader the engine actually offers, or it passes for any string at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from reprolith import (
    archive_report,
    packages_no_time_course_describes,
    reactions_without_rate_laws,
    render_archive_human,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_DATASETS = Path(__file__).parent.parent / "datasets"

#: Three reactions. `r2` carries no `kineticLaw` at all — the estradiol model's 4 — and `r3`
#: carries one that is present and empty — its other 114, and what makes `math is None` the wrong
#: test and `len(math) == 0` the right one.
_ONE_LAW_MISSING = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialConcentration="10"/>
      <species id="B" compartment="c" initialConcentration="0"/>
      <species id="C" compartment="c" initialConcentration="0"/>
      <species id="D" compartment="c" initialConcentration="0"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.5"/></listOfParameters>
    <listOfReactions>
      <reaction id="r1" reversible="false">
        <listOfReactants><speciesReference species="A"/></listOfReactants>
        <listOfProducts><speciesReference species="B"/></listOfProducts>
        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><times/><ci>k</ci><ci>A</ci></apply></math></kineticLaw>
      </reaction>
      <reaction id="r2" reversible="false">
        <listOfReactants><speciesReference species="B"/></listOfReactants>
        <listOfProducts><speciesReference species="C"/></listOfProducts>
      </reaction>
      <reaction id="r3" reversible="false">
        <listOfReactants><speciesReference species="C"/></listOfReactants>
        <listOfProducts><speciesReference species="D"/></listOfProducts>
        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"/></kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>
"""


#: `r3` given a rate, leaving only the absent-law shape.
_NO_KINETIC_LAW = _ONE_LAW_MISSING.replace(
    '<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"/></kineticLaw>',
    '<kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
    "<apply><times/><ci>k</ci><ci>C</ci></apply></math></kineticLaw>",
)

#: `r2` given a rate, leaving only the empty-math shape.
_EMPTY_MATH = _ONE_LAW_MISSING.replace(
    '<listOfProducts><speciesReference species="C"/></listOfProducts>\n      </reaction>',
    '<listOfProducts><speciesReference species="C"/></listOfProducts>\n'
    '        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
    "<apply><times/><ci>k</ci><ci>B</ci></apply></math></kineticLaw>\n      </reaction>",
)


def test_both_ways_a_reaction_can_state_no_rate_are_found() -> None:
    """An absent `kineticLaw` and a present-but-empty one leave the integrator equally empty
    handed, and the second is the one the real deposition uses."""
    assert reactions_without_rate_laws(_ONE_LAW_MISSING) == ("r2", "r3")


def test_a_model_that_states_every_rate_reports_nothing() -> None:
    assert reactions_without_rate_laws(_NO_KINETIC_LAW) == ("r2",)
    assert reactions_without_rate_laws(_EMPTY_MATH) == ("r3",)
    stated = _NO_KINETIC_LAW.replace(
        '<listOfProducts><speciesReference species="C"/></listOfProducts>\n      </reaction>',
        '<listOfProducts><speciesReference species="C"/></listOfProducts>\n'
        '        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        "<apply><times/><ci>k</ci><ci>B</ci></apply></math></kineticLaw>\n      </reaction>",
    )
    assert reactions_without_rate_laws(stated) == ()


def test_every_time_course_model_this_repository_ships_states_all_its_rates() -> None:
    """The check's cost of being wrong is telling an author to repair a correct file, so it is
    swept over every model committed here. The constraint-based one has no rate laws by
    construction and is excluded by its own package, not by an exception for it — which is what
    keeps the exclusion honest when the next fbc model arrives."""
    models = sorted(
        path
        for directory in (_FIXTURES, _DATASETS)
        for path in directory.rglob("*.xml")
    )
    assert len(models) >= 15, "the sweep must actually reach this repository's models"
    checked = 0
    for path in models:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "<sbml" not in text:
            continue
        if packages_no_time_course_describes(text):
            continue
        checked += 1
        assert reactions_without_rate_laws(text) == (), f"{path.name} would be reported"
    assert checked >= 10


def test_the_constraint_based_model_is_excluded_by_its_package_not_by_a_special_case() -> None:
    """Without the gate this check would report all 95 of e_coli_core's reactions and send an
    author to add rate laws to a model that is solved at steady state."""
    text = (_DATASETS / "constraint_based" / "e_coli_core.xml").read_text(encoding="utf-8")
    assert packages_no_time_course_describes(text) == ("fbc",)
    assert len(reactions_without_rate_laws(text)) > 50


def test_libroadrunner_integrates_an_absent_rate_law_as_zero_and_says_nothing() -> None:
    """The quiet failure, and the reason the check exists. If libRoadRunner ever starts refusing
    these files, the report is telling authors something about reproducers that is no longer
    true."""
    roadrunner = pytest.importorskip(
        "roadrunner", reason="the optional 'corroborate' extra (libRoadRunner) is not installed"
    )
    result = roadrunner.RoadRunner(_NO_KINETIC_LAW).simulate(0, 4, 5)
    columns = {name.strip("[]"): index for index, name in enumerate(result.colnames)}
    final = list(result)[-1]
    # r2's flux was zero throughout: everything downstream of the rate-less reaction stayed at its
    # initial value while B accumulated the whole of A. Nothing in the result says so.
    assert final[columns["C"]] == 0.0
    assert final[columns["B"]] > 8.0


def test_libroadrunner_refuses_an_empty_math_element() -> None:
    """The other shape, and the one the estradiol model ships 114 times: loud here, and silent
    above — which is why the check reports both and trusts neither engine to."""
    roadrunner = pytest.importorskip(
        "roadrunner", reason="the optional 'corroborate' extra (libRoadRunner) is not installed"
    )
    with pytest.raises(RuntimeError):
        roadrunner.RoadRunner(_EMPTY_MATH)


@pytest.mark.parametrize("shape", ["absent", "empty"])
def test_the_pinned_engine_imports_it_and_then_abandons_the_run(shape: str) -> None:
    """COPASI does *not* refuse these files — it imports them, starts the course, and stops partway
    with every sample it did produce finite. What turns that into an error is Reprolith's own
    completion check, not the engine, so an author gets a short trajectory and no diagnosis."""
    pytest.importorskip(
        "COPASI", reason="the optional 'engine' extra (python-copasi) is not installed"
    )
    from reprolith import simulate
    from reprolith.engine import NonFiniteSimulation

    text = _NO_KINETIC_LAW if shape == "absent" else _EMPTY_MATH
    with pytest.raises(NonFiniteSimulation) as refused:
        simulate(text, species="B", duration=4.0, steps=4)
    assert "did not complete the time course" in str(refused.value)

    # The control: the same model with every rate stated runs the whole course.
    stated = _NO_KINETIC_LAW.replace(
        '<listOfProducts><speciesReference species="C"/></listOfProducts>\n      </reaction>',
        '<listOfProducts><speciesReference species="C"/></listOfProducts>\n'
        '        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        "<apply><times/><ci>k</ci><ci>B</ci></apply></math></kineticLaw>\n      </reaction>",
    )
    _, values = simulate(stated, species="C", duration=4.0, steps=4)
    assert values[-1] > 2.0


def _archive(sbml: str) -> bytes:
    import io
    import zipfile

    spec = "http://identifiers.org/combine.specifications/"
    manifest = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{spec}omex"/>',
        f'  <content location="./manifest.xml" format="{spec}omex-manifest"/>',
        f'  <content location="./model.xml" format="{spec}sbml"/>',
        "</omexManifest>",
    ])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.xml", manifest)
        zf.writestr("model.xml", sbml)
    return buffer.getvalue()


def test_the_author_check_leads_with_it() -> None:
    """It outranks every other finding because it is not about what a reproducer checks — it is
    about whether there is a run to check. Everything else in the list assumes there is one."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_archive(_ONE_LAW_MISSING))
    assert report["ready_to_submit"] is False
    assert report["fix_list"][0]["kind"] == "rate-law"
    assert report["found"]["reactions_without_rate_laws"] == ["r2", "r3"]
    issue = report["fix_list"][0]["issue"]
    assert "2 of your reactions state no rate law (r2, r3)" in issue
    # The wording has to be true of a file holding either shape, because most hold both: this
    # fixture's r2 is absent and its r3 is empty, and the engines treat those differently.
    assert "abandons the run partway" in issue
    assert "integrates one that is simply absent" in issue
    rendered = render_archive_human(_archive(_ONE_LAW_MISSING))
    assert "state no rate law" in rendered


def test_a_model_stating_all_its_rates_is_never_told_about_rate_laws() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    stated = _NO_KINETIC_LAW.replace(
        '<listOfProducts><speciesReference species="C"/></listOfProducts>\n      </reaction>',
        '<listOfProducts><speciesReference species="C"/></listOfProducts>\n'
        '        <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML">'
        "<apply><times/><ci>k</ci><ci>B</ci></apply></math></kineticLaw>\n      </reaction>",
    )
    report = archive_report(_archive(stated))
    assert report["found"]["reactions_without_rate_laws"] == []
    assert "rate-law" not in {item["kind"] for item in report["fix_list"]}
