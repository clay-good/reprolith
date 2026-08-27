"""The author-facing archive check, read as the author being judged.

`presubmission_report` answers "given the verdict, what should I fix?". This answers the question
before it: an author has an archive and wants to know what a reproducer will find. No model runs.

The interesting tests here are about what the report is *not* allowed to say. Its first version
told an author to "state this in the archive" for the model's own reaction network — a file that
was already correct — and printed a certificate's scope statement over a check that issues no
certificate. Both are pinned below.

Reading a real archive needs libSBML; the wording checks do not.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from reprolith import archive_report, render_archive_human

_ARCHIVE = Path(__file__).parent.parent / "datasets" / "worked_examples" / "metformin_reconstruction.omex"
_SPEC = "http://identifiers.org/combine.specifications/"


def test_something_that_is_not_an_archive_is_the_whole_report() -> None:
    """A malformed archive is the most actionable finding there is, so it is reported rather than
    raised — and nothing else is claimed about a file that could not be read."""
    report = archive_report(b"not a zip at all")
    assert report["ready_to_submit"] is False
    assert report["found"]["readable"] is False
    assert len(report["fix_list"]) == 1
    assert "cannot be read" in report["readiness"]


def test_a_manifest_free_zip_says_what_a_manifest_is_for() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("model.xml", "<sbml/>")
    report = archive_report(buffer.getvalue())
    assert report["ready_to_submit"] is False
    assert "manifest" in report["fix_list"][0]["issue"]


def test_the_check_never_calls_itself_a_certificate() -> None:
    """The certificate scope statement opens "This certificate attests…". Printing it here would
    put a certificate's words on a report that ran no model and reached no verdict."""
    report = archive_report(b"not a zip at all")
    assert "scope" not in report
    assert "issues no certificate" in report["note"]
    rendered = render_archive_human(b"not a zip at all")
    assert "This certificate attests" not in rendered
    assert "WHAT THIS CHECK IS" in rendered


def test_an_extraction_limit_is_never_presented_as_something_to_fix() -> None:
    """The defect this file exists for. A dossier's load-bearing gaps mix two findings: something
    the archive omits (metformin states no unit for 45 of 69 values) and something the archive
    states perfectly well that Reprolith cannot represent (its 35 reactions, its events). The first
    version put both on the fix list under "state this in the archive", which sends an author to
    repair a correct file.
    """
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_ARCHIVE.read_bytes())

    gaps = report["found"]["extraction_gaps"]
    assert any("reaction" in gap["element"] for gap in gaps)
    assert any("units" in gap["element"] for gap in gaps)
    for item in report["fix_list"]:
        assert "state this in the archive" not in item["fix"]
        assert not any(gap["detail"] == item["issue"] for gap in gaps)

    rendered = render_archive_human(_ARCHIVE.read_bytes())
    assert "WHAT REPROLITH'S OWN EXTRACTION WOULD NOT CARRY" in rendered
    assert "Not a fix list" in rendered


def test_readiness_does_not_hinge_on_what_reprolith_cannot_represent() -> None:
    """An archive judged not-ready because of Reprolith's own extraction limits would be telling
    an author their file is wrong when it is Reprolith that is short."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_ARCHIVE.read_bytes())
    assert report["found"]["extraction_gaps"], "this archive should have extraction gaps"
    # Its only genuine finding is that the exported document reports columns rather than plotting
    # results, which is true and is the export's own deliberate choice.
    assert [item["kind"] for item in report["fix_list"]] == ["claims"]


def test_the_report_says_what_the_archive_ships_and_what_can_be_adopted() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    found = archive_report(_ARCHIVE.read_bytes())["found"]
    assert {a["detected_format"] for a in found["files"]} == {"sbml", "sed-ml"}
    # One of the two tasks is over the base model; the other carries the dose override, and an
    # adopted recipe carries no overrides.
    assert found["adoptable_recipes"] == 1
    assert found["claims"]["targetable"] == 0
    assert found["claims"]["not_targetable"] == 2


def _archive_with(members: dict[str, str], manifest: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.xml", manifest)
        for name, text in members.items():
            zf.writestr(name, text)
    return buffer.getvalue()


_MINIMAL_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="X" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.1" constant="true"/></listOfParameters>
    <listOfRules>
      <rateRule variable="X">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>X</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""


def test_a_member_whose_name_starts_with_a_dot_is_still_found() -> None:
    """`lstrip("./")` takes a character *set*, so `.hidden.xml` lost its leading dot and matched
    nothing. The archive reader's own normalizer strips a path prefix, not characters."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml

    sedml = build_experiment_sedml(_MINIMAL_SBML, duration=1.0, steps=10,
                                   model_location=".model.xml")
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{_SPEC}omex-manifest">
  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>
  <content location="./.model.xml" format="{_SPEC}sbml.level-3.version-2"/>
  <content location="./e.sedml" format="{_SPEC}sed-ml" master="true"/>
</omexManifest>
"""
    report = archive_report(
        _archive_with({".model.xml": _MINIMAL_SBML, "e.sedml": sedml}, manifest)
    )
    assert report["found"]["readable"] is True
    assert report["found"]["adoptable_recipes"] == 1


def test_a_model_the_manifest_types_unconventionally_is_still_compared() -> None:
    """A manifest format outside the COMBINE namespace is recorded verbatim, which looked like it
    would leave no artifact typed "sbml" to compare against. It does not: ingestion records the
    model it actually read under its own typing, and that wins over the manifest's. Asserted
    because the report's guard for the opposite case reads as though this were reachable."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import build_experiment_sedml

    sedml = build_experiment_sedml(_MINIMAL_SBML, duration=1.0, steps=10)
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{_SPEC}omex-manifest">
  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>
  <content location="./model.xml" format="application/xml"/>
  <content location="./experiment.sedml" format="{_SPEC}sed-ml" master="true"/>
</omexManifest>
"""
    report = archive_report(
        _archive_with({"model.xml": _MINIMAL_SBML, "experiment.sedml": sedml}, manifest)
    )
    assert report["found"]["readable"] is True
    assert report["found"]["adoptable_recipes"] == 1
    assert not any(item["kind"] == "mismatch" for item in report["fix_list"])
