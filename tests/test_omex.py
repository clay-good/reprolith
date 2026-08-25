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
