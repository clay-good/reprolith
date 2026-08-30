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
import json
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
    # Exactly one task runs the base model; the rest carry a dose override, and an adopted recipe
    # carries none. That stays one however many claims the entry grows, because the claims share
    # a task per distinct dose arm.
    assert found["adoptable_recipes"] == 1
    # Every output the exported document writes is a `report`, never a `plot`: re-reading it must
    # not manufacture published results the paper never staked. So the archive states no
    # targetable claim, and one non-targetable one per claim it expresses.
    assert found["claims"]["targetable"] == 0
    expressed = [c for c in _metformin_claims() if not c.schedule]
    assert found["claims"]["not_targetable"] == len(expressed)


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


def _paper_archive() -> bytes:
    """The archive the metformin paper's own two files make (BioModels ships them unpackaged)."""
    worked = Path(__file__).parent.parent / "datasets" / "worked_examples"
    manifest = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{_SPEC}omex"/>',
        f'  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>',
        f'  <content location="./Zake2021_Metformin_Human_single_PO_dose.xml" format="{_SPEC}sbml"/>',
        f'  <content location="./experiment.sedml" format="{_SPEC}sed-ml" master="true"/>',
        "</omexManifest>",
    ])
    return _archive_with(
        {
            "Zake2021_Metformin_Human_single_PO_dose.xml": (
                worked / "Zake2021_metformin_human_single_PO.xml"
            ).read_text(encoding="utf-8"),
            "experiment.sedml": (
                worked / "Zake2021_metformin_human_single_PO.sedml"
            ).read_text(encoding="utf-8"),
        },
        manifest,
    )


def _metformin_claims() -> list[object]:
    from reprolith import Claim

    dataset = json.loads(
        (Path(__file__).parent.parent / "datasets" / "pkpd_claims.json").read_text(
            encoding="utf-8"
        )
    )
    return [
        Claim.from_record(record)
        for record in dataset["entries"]["BIOMD0000001028"]["claims"]
    ]


def test_without_the_paper_the_check_says_it_did_not_compare_against_it() -> None:
    """A clean fix list must not read as "it runs what your paper reports" when nothing was
    compared against the paper. The count is what separates a passed check from an absent one."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_paper_archive())
    assert report["found"]["manuscript_claims_checked"] == 0
    assert not [item for item in report["fix_list"] if item["kind"] == "manuscript"]
    text = render_archive_human(_paper_archive())
    assert "checked against this experiment: none" in text and "was not checked" in text


def test_the_papers_own_archive_does_not_run_the_dose_the_paper_reports() -> None:
    """The document scans the dose over three values; the paper's 1000 mg claim is none of them.
    Every file validates, which is exactly why this needs saying."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_paper_archive(), claims=_metformin_claims())
    assert report["found"]["manuscript_claims_checked"] == len(_metformin_claims())
    manuscript = [item for item in report["fix_list"] if item["kind"] == "manuscript"]
    assert any(
        "Cmax-1000mg" in item["issue"] and "779.9" in item["issue"] for item in manuscript
    )
    # The two validation-arm claims state their dose in a schedule, not in `parameter_overrides`,
    # and the archive runs neither of those either — so this check must see them. Reading the
    # top-level field alone it saw nothing and said nothing about them.
    for claim in _metformin_claims():
        if not claim.schedule:
            continue
        dose = f"{claim.schedule[-1][1][0][1]:g}"
        assert any(
            f"'{claim.claim_id}'" in item["issue"] and dose in item["issue"]
            for item in manuscript
        ), (claim.claim_id, dose, [i["issue"] for i in manuscript])
    item = manuscript[0]
    # It fails the same way an experiment/model mismatch does — silently — so it ranks with it.
    assert item["priority"] == 1
    assert report["fix_list"][0]["kind"] == "manuscript"


def test_reprolith_own_export_runs_the_claims_it_was_built_from() -> None:
    """The positive control: the exported archive carries the 779.9 override as a `changeAttribute`,
    so the same check that fails the paper's document passes Reprolith's — for the claims the
    document can state.

    Two of this entry's four claims run after a prior administration, which a uniform time course
    cannot express, and the export lists them as unexpressed rather than writing them as plain
    runs. So the archive genuinely does not run their doses, and this check reporting that is the
    two halves agreeing: the writer says it could not state them, and the reader says they are not
    there. What must not happen is the archive claiming to run them.
    """
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_ARCHIVE.read_bytes(), claims=_metformin_claims())
    assert report["found"]["manuscript_claims_checked"] == len(_metformin_claims())
    claims = _metformin_claims()
    reported = {
        claim.claim_id
        for item in report["fix_list"] if item["kind"] == "manuscript"
        for claim in claims
        # Quoted, because these ids nest: "Cmax-500mg" is a prefix of
        # "Cmax-500mg-El-Messaoudi", and a bare substring match reported the wrong claim. The
        # same trap as the README's spelled-out counts, two hours apart.
        if f"'{claim.claim_id}'" in item["issue"]
    }
    # Exactly the scheduled ones: those the document does state are run as certified, and no
    # finding stands against them. Derived from the claims so a sixth does not make this a chore.
    assert reported == {claim.claim_id for claim in claims if claim.schedule}
    assert reported, "no claim here has a schedule; this check would pass vacuously"


def test_claims_supplied_for_an_archive_with_no_experiment_are_not_counted_as_checked() -> None:
    """Nothing compares them: there is no experiment. A count that said otherwise would be a
    number standing in for a check that never ran — the defect this whole check is about."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    manifest = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{_SPEC}omex"/>',
        f'  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>',
        f'  <content location="./m.xml" format="{_SPEC}sbml"/>',
        "</omexManifest>",
    ])
    report = archive_report(
        _archive_with({"m.xml": _MINIMAL_SBML}, manifest), claims=_metformin_claims()
    )
    assert report["found"]["manuscript_claims_checked"] == 0
    text = render_archive_human(
        _archive_with({"m.xml": _MINIMAL_SBML}, manifest), claims=_metformin_claims()
    )
    assert "checked against this experiment: none" in text


_WORKED = Path(__file__).parent.parent / "datasets" / "worked_examples"


def test_a_loose_document_and_model_are_checked_without_packaging_them() -> None:
    """Most papers ship the two files loose — BioModels does, and so does this repository — and
    an author should not have to build an archive to learn what a reproducer would hit."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import pair_report

    report = pair_report(
        (_WORKED / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8"),
        (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8"),
        claims=_metformin_claims(),
    )
    assert report["found"]["assembled_from_loose_files"] is True
    # The same findings the packaged archive gives, reached from the files as they actually ship.
    manuscript = [item for item in report["fix_list"] if item["kind"] == "manuscript"]
    assert any("779.9" in item["issue"] for item in manuscript)


def test_the_pair_check_says_the_manifest_around_it_was_generated() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import render_pair_human

    text = render_pair_human(
        (_WORKED / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8"),
        (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8"),
    )
    assert "assembled here" in text
    assert "not one yet" in text


def test_a_model_named_differently_from_the_documents_source_is_reported() -> None:
    """The model is stored where the document says it is, so the packaging cannot notice the
    file has another name. A reproducer follows the document's source, so the caller that knows
    the name says so and the disagreement is reported rather than smoothed over."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import pair_report

    sedml = (_WORKED / "Zake2021_metformin_human_single_PO.sedml").read_text(encoding="utf-8")
    sbml = (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")

    assert not [
        item for item in pair_report(
            sedml, sbml, model_filename="Zake2021_Metformin_Human_single_PO_dose.xml"
        )["fix_list"] if item["kind"] == "naming"
    ]
    (item,) = [
        item for item in pair_report(sedml, sbml, model_filename="my_model.xml")["fix_list"]
        if item["kind"] == "naming"
    ]
    assert "my_model.xml" in item["issue"]


def test_a_document_running_no_single_model_has_nothing_to_check_against() -> None:
    from reprolith import pair_report

    report = pair_report("<sedML xmlns=\'http://sed-ml.org/sed-ml/level1/version4\'/>", _MINIMAL_SBML)
    assert report["ready_to_submit"] is False
    assert report["found"]["readable"] is False
    assert len(report["fix_list"]) == 1
    assert "0 model files" in report["fix_list"][0]["issue"]


def _fbc_archive() -> bytes:
    """A real constraint-based model, packaged as an archive with no experiment."""
    core = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
    manifest = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{_SPEC}omex"/>',
        f'  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>',
        f'  <content location="./model.xml" format="{_SPEC}sbml"/>',
        "</omexManifest>",
    ])
    return _archive_with({"model.xml": core.read_text(encoding="utf-8")}, manifest)


def test_a_constraint_based_author_is_not_told_to_ship_plots_of_curves() -> None:
    """"Ship a SED-ML document whose plots are the curves your paper shows" is advice about a run
    nobody performs, told to an author whose files may be perfect. It is withheld and named."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_fbc_archive())
    assert [item["kind"] for item in report["fix_list"]] == []
    assert [entry["package"] for entry in report["found"]["not_a_time_course"]] == ["fbc"]
    assert "solved at steady state" in report["readiness"]


def test_a_model_this_check_cannot_judge_is_not_reported_as_ready() -> None:
    """Green would say a reproducer knows what to check, which nothing here established."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    assert archive_report(_fbc_archive())["ready_to_submit"] is False
    text = render_archive_human(_fbc_archive())
    assert "WHAT THIS CHECK DID NOT JUDGE" in text
    # And the fix list does not congratulate the author under a NOT YET READY headline.
    assert "a reproducer can read this archive and knows what to check" not in text


def test_a_time_course_model_is_judged_as_before() -> None:
    """The withholding is the package's doing, not a hole: an ODE archive still gets the items."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_ARCHIVE.read_bytes())
    assert report["found"]["not_a_time_course"] == []
    assert [item["kind"] for item in report["fix_list"]] == ["claims"]


_KINETIC = Path(__file__).parent.parent / "datasets" / "kinetic"


def _plotting_archive() -> bytes:
    """The real SED-ML BioModels ships for Kholodenko: four plotted curves, no values."""
    sbml = (_KINETIC / "BIOMD0000000010.xml").read_text(encoding="utf-8")
    sedml = (_KINETIC / "BIOMD0000000010.sedml").read_text(encoding="utf-8")
    manifest = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{_SPEC}omex-manifest">
  <content location="." format="{_SPEC}omex"/>
  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>
  <content location="./BIOMD0000000010_url.xml" format="{_SPEC}sbml.level-2.version-4"/>
  <content location="./BIOMD0000000010.sedml" format="{_SPEC}sed-ml.level-1.version-4" master="true"/>
</omexManifest>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.xml", manifest)
        zf.writestr("BIOMD0000000010_url.xml", sbml)
        zf.writestr("BIOMD0000000010.sedml", sedml)
    return buffer.getvalue()


def test_curves_with_no_values_are_reported_and_do_not_hold_up_the_submission() -> None:
    """The step between this archive and a checked claim, told to the one person who can remove it.

    Publishing results as figures is what papers do, and a document that plots its curves is doing
    its job — so this is reported and never gated on. An archive marked NOT YET READY for it would
    tell almost every honest author their work is broken, which is the strict direction and the
    expensive mistake.
    """
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_plotting_archive())

    assert report["ready_to_submit"] is True  # the report is advice here, not a gate
    assert [item["kind"] for item in report["fix_list"]] == []
    unvalued = report["found"]["curves_without_values"]
    assert len(unvalued) == 4
    assert all(item["claim_id"] and item["source_location"] for item in unvalued)

    text = render_archive_human(_plotting_archive())
    assert "WHAT A REPRODUCER WOULD HAVE TO READ OFF YOUR FIGURES" in text
    assert "does not hold up your submission" in text
    # The consequence, and the cheap way out of it — the author has the numbers.
    assert "band twice as wide as a number you print" in text
    assert "dataDescription selecting one column per curve" in text


def test_an_archive_whose_curves_carry_values_is_not_told_to_ship_them() -> None:
    """The section is absent, not empty: there is nothing for a reproducer to read off a picture."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    report = archive_report(_ARCHIVE.read_bytes())
    assert report["found"]["curves_without_values"] == []
    assert "WHAT A REPRODUCER WOULD HAVE TO READ OFF YOUR FIGURES" not in render_archive_human(
        _ARCHIVE.read_bytes()
    )
