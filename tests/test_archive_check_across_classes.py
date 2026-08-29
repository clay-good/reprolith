"""The author check, handed one real model from every class the repository ships.

The defect that produced this file: pointed at a constraint-based archive, the check said "ship a
SED-ML document whose plots are the curves your paper shows". An fbc model is solved at steady
state; there are no curves, and the author's files may be perfect. It was invisible from inside the
check, and visible in one second from outside it.

So the check now meets each class's real committed model. What is asserted is not a verdict — these
archives are assembled here and prove nothing about their papers — but the properties that must
hold whatever the class is: it does not raise, it never advises a time-course fix for a model no
time course describes, and it names what it could not judge instead of staying silent about it.

Needs libSBML to read a model, so it skips on the dependency-free gate.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from reprolith import archive_report, render_archive_human

_DATASETS = Path(__file__).parent.parent / "datasets"
_SPEC = "http://identifiers.org/combine.specifications/"

#: One real model per class the repository ships as a file, with whether a time course describes it.
_MODELS = [
    ("kinetic", _DATASETS / "kinetic" / "BIOMD0000000010.xml", True),
    ("kinetic", _DATASETS / "kinetic" / "BIOMD0000000005.xml", True),
    ("pkpd", _DATASETS / "worked_examples" / "Zake2021_metformin_human_single_PO.xml", True),
    ("constraint-based", _DATASETS / "constraint_based" / "e_coli_core.xml", False),
    ("logical", _DATASETS / "logical" / "worked_example" / "model.xml", False),
]

#: The fixes that only make sense for a model a time course describes. Telling the author of a
#: constraint-based or logical model to do any of these is advice about a run nobody performs —
#: `rate-law` most literally of all: e_coli_core has no rate laws for any of its 95 reactions and
#: is not missing a thing.
_TIME_COURSE_ONLY = {"claims", "recipe", "rate-law"}


def _archive(sbml: str) -> bytes:
    manifest = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{_SPEC}omex"/>',
        f'  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>',
        f'  <content location="./model.xml" format="{_SPEC}sbml"/>',
        "</omexManifest>",
    ])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.xml", manifest)
        zf.writestr("model.xml", sbml)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("label", "path", "is_time_course"),
    [pytest.param(label, path, tc, id=f"{label}-{path.stem}") for label, path, tc in _MODELS],
)
def test_the_check_says_only_what_applies_to_this_kind_of_model(
    label: str, path: Path, is_time_course: bool
) -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_archive(path.read_text(encoding="utf-8")))
    kinds = {item["kind"] for item in report["fix_list"]}
    withheld = [entry["package"] for entry in report["found"]["not_a_time_course"]]

    if is_time_course:
        assert withheld == [], f"{label}: nothing should be withheld for a time-course model"
        # These archives ship no experiment, so the one thing every reproducer needs is missing.
        assert "claims" in kinds, f"{label}: an archive stating no result should say so"
    else:
        assert withheld, f"{label}: a model no time course describes must say what was not judged"
        assert not (kinds & _TIME_COURSE_ONLY), (
            f"{label}: told the author to fix something a {withheld} model does not have: {kinds}"
        )
        assert report["ready_to_submit"] is False, (
            f"{label}: ready would claim a reproducer knows what to check, which was not judged"
        )
        assert "WHAT THIS CHECK DID NOT JUDGE" in render_archive_human(
            _archive(path.read_text(encoding="utf-8"))
        )
