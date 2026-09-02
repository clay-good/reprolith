"""COMBINE-archive intake (spec: paper-ingestion, "Artifact intake and typing"; roadmap #4).

The archives here are built in the test from the SBML and SED-ML BioModels actually ships for the
Kholodenko MAPK model (``datasets/kinetic/``), packaged per the COMBINE archive specification. The
files are real; the zip around them is assembled here because the repository does not vendor a
``.omex``.

Reading the manifest and refusing an ambiguous archive is pure standard library, so those tests run
in the dependency-free core gate. The tests that actually ingest the model need the ``engine``
extra and skip without it.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from reprolith import ingest_omex

_KINETIC = Path(__file__).parent.parent / "datasets" / "kinetic"
_SBML = (_KINETIC / "BIOMD0000000010.xml").read_text(encoding="utf-8")
_SEDML = (_KINETIC / "BIOMD0000000010.sedml").read_text(encoding="utf-8")

_SPEC = "http://identifiers.org/combine.specifications/"


def _manifest(*entries: tuple[str, str, bool]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
        f'  <content location="." format="{_SPEC}omex"/>',
        f'  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>',
    ]
    for location, fmt, master in entries:
        master_attr = ' master="true"' if master else ""
        lines.append(f'  <content location="{location}" format="{fmt}"{master_attr}/>')
    lines.append("</omexManifest>")
    return "\n".join(lines)


def _archive(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _kholodenko_archive(**extra: str) -> bytes:
    """The archive BioModels' own two files would make, plus anything a test adds."""
    return _archive({
        "manifest.xml": _manifest(
            ("./BIOMD0000000010_url.xml", f"{_SPEC}sbml.level-2.version-4", False),
            ("./BIOMD0000000010.sedml", f"{_SPEC}sed-ml.level-1.version-4", True),
            *[(f"./{name}", "application/pdf", False) for name in extra if name.endswith(".pdf")],
        ),
        "BIOMD0000000010_url.xml": _SBML,
        "BIOMD0000000010.sedml": _SEDML,
        **extra,
    })


# --- the whole point: one file in, structure and claims out --------------------------


def test_an_archive_yields_the_model_structure_and_the_documents_claims() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    dossier = ingest_omex(_kholodenko_archive(), entry="BIOMD0000000010")

    # The SED-ML names the model file, and the model is ingested from inside the archive.
    assert "MAPK_PP" in dossier.state_variables
    assert dossier.validate() == []
    # The experiment's two figures, four curves, are the dossier's targets.
    assert [c.quantity for c in dossier.targetable_claims()] == [
        "MAPK_PP", "MAPK", "MAPK_PP", "MAPK",
    ]
    formats = {a.filename: a.detected_format for a in dossier.artifacts}
    assert formats["BIOMD0000000010_url.xml"] == "sbml"
    assert formats["BIOMD0000000010.sedml"] == "sed-ml"
    ingested = next(a for a in dossier.artifacts if a.filename.endswith("_url.xml"))
    assert ingested.validates is True


def test_a_file_the_manifest_never_lists_is_recorded_rather_than_dropped() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    archive = _kholodenko_archive(**{"notes.txt": "read me"})
    dossier = ingest_omex(archive, entry="BIOMD0000000010")

    formats = {a.filename: a.detected_format for a in dossier.artifacts}
    assert formats["notes.txt"] == "unlisted"  # malformed archive, but the file is still shipped
    assert "manifest.xml" not in formats  # the manifest is not one of the things it describes


def test_an_archive_shipping_only_a_model_has_structure_and_no_claims() -> None:
    """Nothing in it says which results the paper published, so it stakes none."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    archive = _archive({
        "manifest.xml": _manifest(("./model.xml", f"{_SPEC}sbml.level-2.version-4", False)),
        "model.xml": _SBML,
    })
    dossier = ingest_omex(archive, entry="BIOMD0000000010")
    assert dossier.state_variables and dossier.claims == ()


def test_a_model_source_resolves_relative_to_the_document_that_names_it() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    sedml = _SEDML.replace('source="BIOMD0000000010_url.xml"', 'source="../models/mapk.xml"')
    archive = _archive({
        "manifest.xml": _manifest(
            ("./models/mapk.xml", f"{_SPEC}sbml", False),
            ("./experiments/figures.sedml", f"{_SPEC}sed-ml", True),
        ),
        "models/mapk.xml": _SBML,
        "experiments/figures.sedml": sedml,
    })
    dossier = ingest_omex(archive, entry="BIOMD0000000010")
    assert [a.filename for a in dossier.artifacts if a.detected_format == "sbml"] == [
        "models/mapk.xml"
    ]
    assert len(dossier.targetable_claims()) == 4


# --- what it refuses to guess --------------------------------------------------------


def test_a_zip_without_a_manifest_is_not_an_archive() -> None:
    with pytest.raises(ValueError, match="no manifest.xml"):
        ingest_omex(_archive({"model.xml": _SBML}), entry="x")


def test_unreadable_bytes_are_reported_as_an_unreadable_archive() -> None:
    with pytest.raises(ValueError, match="not a readable COMBINE archive"):
        ingest_omex(b"PK\x03\x04 not really a zip", entry="x")


def test_several_experiments_with_none_singled_out_are_refused() -> None:
    """Which experiment the paper ran is the archive's to say; picking one would invent it."""
    archive = _archive({
        "manifest.xml": _manifest(
            ("./model.xml", f"{_SPEC}sbml", False),
            ("./a.sedml", f"{_SPEC}sed-ml", False),
            ("./b.sedml", f"{_SPEC}sed-ml", False),
        ),
        "model.xml": _SBML, "a.sedml": _SEDML, "b.sedml": _SEDML,
    })
    with pytest.raises(ValueError, match="does not single out one simulation experiment"):
        ingest_omex(archive, entry="x")


def test_the_master_document_is_the_experiment_when_one_is_marked() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    single_figure = _SEDML.replace('<plot2D id="plot_1" name="Figure 2B">', '<plot2D id="unused">')
    archive = _archive({
        "manifest.xml": _manifest(
            ("./BIOMD0000000010_url.xml", f"{_SPEC}sbml", False),
            ("./both.sedml", f"{_SPEC}sed-ml", True),
            ("./one.sedml", f"{_SPEC}sed-ml", False),
        ),
        "BIOMD0000000010_url.xml": _SBML, "both.sedml": _SEDML, "one.sedml": single_figure,
    })
    claims = ingest_omex(archive, entry="x").targetable_claims()
    assert [c.source_location.split(",")[0] for c in claims][-1].endswith("(Figure 2B)")


def test_an_experiment_over_several_models_is_refused() -> None:
    """A dossier is the extraction of one model; the archive has to say which one."""
    two_models = _SEDML.replace(
        '<model id="kholodenko_b" language="urn:sedml:language:sbml.level-2.version-4" source="#kholodenko">',
        '<model id="kholodenko_b" language="urn:sedml:language:sbml.level-2.version-4" source="other.xml">',
    )
    archive = _archive({
        "manifest.xml": _manifest(
            ("./BIOMD0000000010_url.xml", f"{_SPEC}sbml", False),
            ("./other.xml", f"{_SPEC}sbml", False),
            ("./e.sedml", f"{_SPEC}sed-ml", True),
        ),
        "BIOMD0000000010_url.xml": _SBML, "other.xml": _SBML, "e.sedml": two_models,
    })
    with pytest.raises(ValueError, match="runs 2 model files"):
        ingest_omex(archive, entry="x")


def test_an_experiment_whose_model_is_missing_from_the_archive_is_refused() -> None:
    archive = _archive({
        "manifest.xml": _manifest(("./e.sedml", f"{_SPEC}sed-ml", True)),
        "e.sedml": _SEDML,
    })
    with pytest.raises(ValueError, match="which the archive does not contain"):
        ingest_omex(archive, entry="x")


def test_an_archive_with_no_experiment_and_several_models_is_refused() -> None:
    archive = _archive({
        "manifest.xml": _manifest(
            ("./a.xml", f"{_SPEC}sbml", False), ("./b.xml", f"{_SPEC}sbml", False),
        ),
        "a.xml": _SBML, "b.xml": _SBML,
    })
    with pytest.raises(ValueError, match="no SED-ML experiment and 2 SBML models"):
        ingest_omex(archive, entry="x")


def test_a_manifest_entry_the_archive_does_not_ship_is_a_gap_not_an_artifact() -> None:
    """Recording it as an artifact would say the paper ships a file it does not."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    archive = _archive({
        "manifest.xml": _manifest(
            ("./BIOMD0000000010_url.xml", f"{_SPEC}sbml", False),
            ("./BIOMD0000000010.sedml", f"{_SPEC}sed-ml", True),
            ("./supplement.pdf", "application/pdf", False),
        ),
        "BIOMD0000000010_url.xml": _SBML,
        "BIOMD0000000010.sedml": _SEDML,
    })
    dossier = ingest_omex(archive, entry="BIOMD0000000010")

    assert "supplement.pdf" not in {a.filename for a in dossier.artifacts}
    missing = [g for g in dossier.gaps if g.element == "supplement.pdf"]
    assert len(missing) == 1 and "does not contain it" in missing[0].detail


# --- the experiment and the model have to agree --------------------------------------

_APOS = "&apos;"


def test_the_shipped_pair_agrees_with_itself() -> None:
    """The check earns its keep only if it is quiet on a real, correct archive."""
    from reprolith import archive_mismatches

    assert archive_mismatches(_SEDML, _SBML) == []


def test_an_observed_species_the_model_does_not_define_is_reported() -> None:
    from reprolith import archive_mismatches

    broken = _SEDML.replace(
        f"species[@id={_APOS}MAPK_PP{_APOS}]", f"species[@id={_APOS}MAPK_PPP{_APOS}]"
    )
    assert broken != _SEDML
    problems = archive_mismatches(broken, _SBML)
    assert problems and all("MAPK_PPP" in p and "observes" in p for p in problems)


def test_an_override_aimed_at_the_wrong_reaction_is_reported() -> None:
    """A flat search for the id would pass: KK2 exists — inside J1, not the J0 aimed at here."""
    from reprolith import archive_mismatches

    misaimed = _SEDML.replace(
        f"reaction[@id={_APOS}J1{_APOS}]/sbml:kineticLaw/sbml:listOfParameters/"
        f"sbml:parameter[@id={_APOS}KK2{_APOS}]",
        f"reaction[@id={_APOS}J0{_APOS}]/sbml:kineticLaw/sbml:listOfParameters/"
        f"sbml:parameter[@id={_APOS}KK2{_APOS}]",
    )
    assert misaimed != _SEDML
    problems = archive_mismatches(misaimed, _SBML)
    assert len(problems) == 1 and "changes" in problems[0] and "J0" in problems[0]


def test_a_target_this_resolver_cannot_read_is_not_called_a_mismatch() -> None:
    """Not resolving a path is not evidence the model lacks the element."""
    from reprolith import archive_mismatches

    by_name = _SEDML.replace(
        f"species[@id={_APOS}MAPK_PP{_APOS}]", f"species[@name={_APOS}MAPK_PP{_APOS}]"
    )
    assert by_name != _SEDML
    assert archive_mismatches(by_name, _SBML) == []


def test_an_inconsistent_archive_records_the_mismatch_as_a_load_bearing_gap() -> None:
    """An override that overrides nothing runs the unmodified model, so the gap is load-bearing."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    broken = _SEDML.replace(f"parameter[@id={_APOS}Ki{_APOS}]", f"parameter[@id={_APOS}Kj{_APOS}]")
    archive = _archive({
        "manifest.xml": _manifest(
            ("./BIOMD0000000010_url.xml", f"{_SPEC}sbml", False),
            ("./BIOMD0000000010.sedml", f"{_SPEC}sed-ml", True),
        ),
        "BIOMD0000000010_url.xml": _SBML, "BIOMD0000000010.sedml": broken,
    })
    dossier = ingest_omex(archive, entry="BIOMD0000000010")

    flagged = [g for g in dossier.load_bearing_gaps() if "Kj" in g.element]
    assert len(flagged) == 1 and "which the model does not have" in flagged[0].detail
    # The healthy pair records no such gap.
    healthy = ingest_omex(_kholodenko_archive(), entry="BIOMD0000000010")
    assert [g for g in healthy.gaps if "which the model does not have" in g.detail] == []


def test_a_member_stored_with_a_leading_dot_slash_is_the_same_file() -> None:
    """Zips and manifests write `./model.xml` and `model.xml` interchangeably."""
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

    archive = _archive({
        "./manifest.xml": _manifest(
            ("BIOMD0000000010_url.xml", f"{_SPEC}sbml", False),
            ("./BIOMD0000000010.sedml", f"{_SPEC}sed-ml", True),
        ),
        "./BIOMD0000000010_url.xml": _SBML,
        "BIOMD0000000010.sedml": _SEDML,
    })
    dossier = ingest_omex(archive, entry="BIOMD0000000010")
    assert len(dossier.targetable_claims()) == 4
    assert "unlisted" not in {a.detected_format for a in dossier.artifacts}


def test_a_descendant_axis_target_is_unresolvable_not_missing() -> None:
    """`//sbml:species[@id='MAPK_PP']` names a species the model *has*.

    Walking direct children cannot answer a descendant axis, and answering "absent" accuses a
    correct archive — the failure this check's own contract says it must not make.
    """
    from reprolith import archive_mismatches

    short = _SEDML.replace(
        f"/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id={_APOS}MAPK_PP{_APOS}]",
        f"//sbml:species[@id={_APOS}MAPK_PP{_APOS}]",
    )
    assert short != _SEDML
    assert archive_mismatches(short, _SBML) == []


def test_a_target_anchored_somewhere_else_is_unresolvable_not_missing() -> None:
    """A path that does not start at the model document cannot be walked from its root."""
    from reprolith import archive_mismatches

    elsewhere = _SEDML.replace("/sbml:sbml/sbml:model/sbml:listOfSpecies/", "sbml:model/sbml:listOfSpecies/")
    assert elsewhere != _SEDML
    assert archive_mismatches(elsewhere, _SBML) == []


def test_the_two_readers_of_an_archive_locate_the_same_pair() -> None:
    """`archive_documents` hands back the documents `ingest_omex` ingests, from the same code.

    The locating logic — which member is the experiment, which model it runs, and every way that
    can fail to single out one pair — is shared. Two readers resolving an archive independently
    is how they come to disagree about what it ships.
    """
    from reprolith.omex import archive_documents

    sedml, model = archive_documents(_kholodenko_archive())
    assert sedml == _SEDML
    assert model == _SBML
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    assert ingest_omex(_kholodenko_archive(), entry="BIOMD0000000010").claims


def test_a_reader_of_the_documents_refuses_what_ingestion_refuses() -> None:
    """A zip with no manifest is not an archive, whichever reader opens it."""
    from reprolith.omex import archive_documents

    with pytest.raises(ValueError, match="no manifest.xml"):
        archive_documents(_archive({"model.xml": _SBML}))


def test_a_member_that_expands_past_the_cap_is_refused_not_read() -> None:
    """A compressed size says nothing about a decompressed one.

    Every reader here — `archive-check`, `figure-check`, the ingester — is pointed at a file
    somebody else produced, and a kilobyte of zeroes expands to a gigabyte. The MCP surface already
    bounds its lint inputs for the same reason, after one entirely legal request cost 1.7 GB.

    Checked at a small cap rather than by building a real bomb: the guard is a comparison, and a
    test that spends a gigabyte to exercise it is its own denial of service.
    """
    import io
    import zipfile

    from reprolith import omex

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.xml", "0" * 4096)
    buffer.seek(0)

    with zipfile.ZipFile(buffer) as archive:
        # Under the cap, it reads.
        assert len(omex._read_member(archive, "manifest.xml")) == 4096

        original = omex._MAX_MEMBER_BYTES
        try:
            omex._MAX_MEMBER_BYTES = 100
            with pytest.raises(ValueError, match="above the 100-byte cap"):
                omex._read_member(archive, "manifest.xml")
        finally:
            omex._MAX_MEMBER_BYTES = original


def test_a_header_that_understates_its_member_is_caught_by_the_zip_itself() -> None:
    """Why consulting the declared size is not trusting it.

    The cap is checked against the size the archive declares, which a hostile file writes for
    itself — so the read is bounded again afterwards. That second bound is a backstop rather than
    the guard: Python's own reader stops at the declared size and then fails the CRC, so a header
    that understates its member cannot smuggle bytes past the first check. Pinned because the
    first check's trustworthiness rests on it.
    """
    import io
    import zipfile

    from reprolith import omex

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.xml", "0" * 4096)
    buffer.seek(0)

    with zipfile.ZipFile(buffer) as archive:
        archive.getinfo("manifest.xml").file_size = 1  # a header that lies about a 4 KiB member
        with pytest.raises(zipfile.BadZipFile):
            omex._read_member(archive, "manifest.xml")
