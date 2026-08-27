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
