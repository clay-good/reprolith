"""Values a document ships (spec: paper-ingestion; roadmap #4).

`enumerate_sedml_claims` used to say, in its own docstring, that reference values shipped through
a `dataDescription` "are not read yet, so a document carrying real experimental data is currently
marked figure-referenced like any other". Two things were wrong with that: the values were sitting
in the archive, and the curve plotting them was being listed as a result the *model* must
reproduce — the paper's own measurements, on the list of things to regenerate, then abstained on
for want of a reference the document was shipping all along.

The document below is synthetic, and says so: no archive in this repository's corpus uses a data
description. It is standard-conformant, which is checkable — libSEDML, an independent
implementation, reads it with zero errors (pinned below where the `validate` extra is installed).

Pure standard library, so this runs in the dependency-free core gate.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from reprolith import (
    ReferenceKind,
    enumerate_sedml_claims,
    read_sedml_data,
    sedml_data_sources,
)

_CSV = "time,C_observed,note\n0,0.0,start\n1,4.2,peak\n2,6.1,end\n"

_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="m">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.1" constant="true"/></listOfParameters>
    <listOfRules>
      <rateRule variable="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>C</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""


def _document(*, source: str = "observed.csv", fmt: str = "urn:sedml:format:csv",
              slice_value: str = "C_observed", extra_source: str = "") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version4" level="1" version="4">
  <listOfDataDescriptions>
    <dataDescription id="obs" name="observed" source="{source}" format="{fmt}">
      <dimensionDescription>
        <compositeDescription xmlns="http://www.numl.org/numl/level1/version1"
                              indexType="double" id="Index" name="Index">
          <compositeDescription indexType="string" id="ColumnIds" name="ColumnIds">
            <atomicDescription valueType="double" name="Values"/>
          </compositeDescription>
        </compositeDescription>
      </dimensionDescription>
      <listOfDataSources>
        <dataSource id="observedC">
          <listOfSlices><slice reference="ColumnIds" value="{slice_value}"/></listOfSlices>
        </dataSource>
        <dataSource id="rowIndex" indexSet="Index"/>
        {extra_source}
      </listOfDataSources>
    </dataDescription>
  </listOfDataDescriptions>
  <listOfModels>
    <model id="model" language="urn:sedml:language:sbml" source="m.xml"/>
  </listOfModels>
  <listOfSimulations>
    <uniformTimeCourse id="sim" initialTime="0" outputStartTime="0" outputEndTime="24"
                       numberOfSteps="240"/>
  </listOfSimulations>
  <listOfTasks>
    <task id="task" modelReference="model" simulationReference="sim"/>
  </listOfTasks>
  <listOfDataGenerators>
    <dataGenerator id="g_time" name="time">
      <listOfVariables>
        <variable id="v_time" symbol="urn:sedml:symbol:time" taskReference="task"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_time</ci></math>
    </dataGenerator>
    <dataGenerator id="g_C" name="C">
      <listOfVariables>
        <variable id="v_C" target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='C']"
                  taskReference="task"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_C</ci></math>
    </dataGenerator>
    <dataGenerator id="g_obs" name="observed C">
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>observedC</ci></math>
    </dataGenerator>
  </listOfDataGenerators>
  <listOfOutputs>
    <plot2D id="fig1" name="Figure 1">
      <listOfCurves>
        <curve id="c_sim" logX="false" logY="false" xDataReference="g_time" yDataReference="g_C"/>
        <curve id="c_obs" logX="false" logY="false" xDataReference="g_time" yDataReference="g_obs"/>
      </listOfCurves>
    </plot2D>
  </listOfOutputs>
</sedML>
"""


def test_the_document_is_valid_sedml_by_an_independent_implementation() -> None:
    """The fixture is synthetic, so its conformance is checked rather than assumed."""
    libsedml = pytest.importorskip("libsedml", reason="the optional 'validate' extra")
    document = libsedml.readSedMLFromString(_document())
    assert document.getNumErrors() == 0


def test_the_files_a_document_names_are_enumerable() -> None:
    assert sedml_data_sources(_document()) == ("observed.csv",)


def test_a_column_a_slice_names_is_read() -> None:
    assert read_sedml_data(_document(), {"observed.csv": _CSV}) == {"observedC": (0.0, 4.2, 6.1)}


def test_an_index_set_is_not_values() -> None:
    """`rowIndex` selects row labels, not a series, so it is absent rather than guessed at."""
    assert "rowIndex" not in read_sedml_data(_document(), {"observed.csv": _CSV})


def test_a_non_numeric_column_is_not_a_reference() -> None:
    data = read_sedml_data(_document(slice_value="note"), {"observed.csv": _CSV})
    assert data == {}


def test_a_format_this_does_not_parse_is_left_alone() -> None:
    """NuML is an XML container; a column read out of a format nobody parsed would be invented."""
    data = read_sedml_data(
        _document(fmt="urn:sedml:format:numl"), {"observed.csv": _CSV}
    )
    assert data == {}


def test_a_file_that_was_not_supplied_yields_nothing() -> None:
    assert read_sedml_data(_document(), {}) == {}


def test_a_data_curve_is_not_a_result_the_model_must_reproduce() -> None:
    data = read_sedml_data(_document(), {"observed.csv": _CSV})
    claims = {claim.id: claim for claim in enumerate_sedml_claims(_document(), data=data)}

    simulated, observed = claims["c_sim"], claims["c_obs"]
    assert simulated.targetable and simulated.reference_kind is ReferenceKind.DIGITIZED_FIGURE
    assert not observed.targetable
    assert observed.reference_kind is ReferenceKind.NUMERIC
    assert observed.reference_data == (0.0, 4.2, 6.1)
    assert "data source 'observedC'" in observed.source_location


def test_the_pairing_between_a_data_curve_and_a_simulated_one_is_not_invented() -> None:
    """SED-ML does not say the data curve is the reference for the simulated one, so neither
    does the dossier: the simulated claim keeps no reference values."""
    data = read_sedml_data(_document(), {"observed.csv": _CSV})
    simulated = next(c for c in enumerate_sedml_claims(_document(), data=data) if c.id == "c_sim")
    assert simulated.reference_data == ()


def test_without_the_data_the_curve_keeps_its_provenance_and_no_values() -> None:
    observed = next(c for c in enumerate_sedml_claims(_document()) if c.id == "c_obs")
    assert not observed.targetable
    assert observed.reference_data == ()
    assert "the document ships" in observed.source_location


_SPEC = "http://identifiers.org/combine.specifications/"


def _archive(*, include_data: bool = True) -> bytes:
    entries = [
        ("./m.xml", f"{_SPEC}sbml"),
        ("./experiment.sedml", f"{_SPEC}sed-ml"),
    ] + ([("./observed.csv", "text/csv")] if include_data else [])
    manifest = "\n".join(
        ['<?xml version="1.0" encoding="UTF-8"?>',
         '<omexManifest xmlns="http://identifiers.org/combine.specifications/omex-manifest">',
         f'  <content location="." format="{_SPEC}omex"/>',
         f'  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>']
        + [f'  <content location="{loc}" format="{fmt}"'
           + (' master="true"' if loc.endswith(".sedml") else "")
           + "/>" for loc, fmt in entries]
        + ["</omexManifest>"]
    )
    members = {"manifest.xml": manifest, "m.xml": _SBML, "experiment.sedml": _document()}
    if include_data:
        members["observed.csv"] = _CSV
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return buffer.getvalue()


def test_an_archive_reads_the_values_its_document_ships() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import ingest_omex

    dossier = ingest_omex(_archive(), entry="synthetic")
    observed = next(c for c in dossier.claims if c.id == "c_obs")
    assert observed.reference_data == (0.0, 4.2, 6.1)
    # The values are the paper's, not a result the model owes; the simulated curve is the claim.
    assert [c.id for c in dossier.targetable_claims()] == ["c_sim"]


def test_a_data_file_the_archive_does_not_ship_is_a_gap_not_an_empty_reference() -> None:
    pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
    from reprolith import ingest_omex

    dossier = ingest_omex(_archive(include_data=False), entry="synthetic")
    (gap,) = [gap for gap in dossier.gaps if gap.element == "observed.csv"]
    assert "does not contain" in gap.detail
    observed = next(c for c in dossier.claims if c.id == "c_obs")
    assert observed.reference_data == ()


def test_a_curve_that_reads_the_data_and_the_model_stays_a_simulated_claim() -> None:
    """A trace normalized by its own data asserts something about the model, and the raw column
    is not the values of the ratio anyone plotted."""
    mixed = _document().replace(
        '<math xmlns="http://www.w3.org/1998/Math/MathML"><ci>observedC</ci></math>\n'
        "    </dataGenerator>",
        '<listOfVariables>\n'
        '        <variable id="v_C2" '
        "target=\"/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='C']\" "
        'taskReference="task"/>\n'
        "      </listOfVariables>\n"
        '      <math xmlns="http://www.w3.org/1998/Math/MathML">'
        "<apply><divide/><ci>v_C2</ci><ci>observedC</ci></apply></math>\n"
        "    </dataGenerator>",
    )
    data = read_sedml_data(mixed, {"observed.csv": _CSV})
    claim = next(c for c in enumerate_sedml_claims(mixed, data=data) if c.id == "c_obs")
    assert claim.targetable
    assert claim.reference_data == ()
    assert claim.reference_kind is ReferenceKind.DIGITIZED_FIGURE


def test_a_byte_order_mark_does_not_hide_the_first_column() -> None:
    """A spreadsheet-saved CSV opens with a BOM, which lands on the first header cell and nothing
    else — so a slice naming the first column silently matched nothing while the rest worked."""
    document = _document(slice_value="time")
    assert read_sedml_data(document, {"observed.csv": _CSV}) == {
        "observedC": (0.0, 1.0, 2.0)
    }
    assert read_sedml_data(document, {"observed.csv": "\ufeff" + _CSV}) == {
        "observedC": (0.0, 1.0, 2.0)
    }


_UNREADABLE_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version4" level="1" version="4">
  <listOfDataDescriptions>
    <dataDescription id="d_numl" source="obs.numl" format="urn:sedml:format:numl"/>
    <dataDescription id="d_absent" source="missing.csv" format="urn:sedml:format:csv"/>
    <dataDescription id="d_csv" source="obs.csv" format="urn:sedml:format:csv">
      <listOfDataSources>
        <dataSource id="s_good">
          <listOfSlices><slice reference="c" value="conc"/></listOfSlices>
        </dataSource>
        <dataSource id="s_index" indexSet="rows"/>
        <dataSource>
          <listOfSlices><slice value="conc"/></listOfSlices>
        </dataSource>
        <dataSource id="s_no_column">
          <listOfSlices><slice value="absent"/></listOfSlices>
        </dataSource>
        <dataSource id="s_two_slices">
          <listOfSlices><slice value="conc"/><slice value="time"/></listOfSlices>
        </dataSource>
      </listOfDataSources>
    </dataDescription>
  </listOfDataDescriptions>
</sedML>
"""


def test_every_reason_a_series_goes_unread_is_reported_and_named() -> None:
    """Six ways to lose the author's own measurements, each previously a bare `continue`.

    The symptom of any of them is a claim with no reference values, which is indistinguishable
    from a paper that published none — so an author shipping a NuML file, or naming a source their
    archive does not contain, was told nothing at all. Each reason names the description or the
    source it is about, because "some data could not be read" is not actionable.
    """
    from reprolith import read_sedml_data, unreadable_data_descriptions

    files = {"obs.csv": "time,conc\n0,1\n1,2\n"}
    reasons = unreadable_data_descriptions(_UNREADABLE_DOC, files)
    assert len(reasons) == 5, reasons
    joined = "\n".join(reasons)
    for expected in ("d_numl", "d_absent", "s_no_column", "s_two_slices"):
        assert expected in joined, expected
    assert "states no id" in joined
    # And *not* the indexSet source. It is skipped by the reader for a good reason — an indexSet
    # names row labels — but that is normal in a conformant document, so reporting it would raise
    # a false alarm on every archive that ships one, this file's own correct fixture included.
    assert "s_index" not in joined

    # And the one readable source is still read: a diagnostic that reported everything as broken
    # would be as useless as one that reported nothing.
    assert read_sedml_data(_UNREADABLE_DOC, files) == {"s_good": (1.0, 2.0)}


def test_a_document_whose_series_all_read_reports_no_reason() -> None:
    """The half that makes it a check rather than a nuisance."""
    from reprolith import read_sedml_data, unreadable_data_descriptions

    files = {"observed.csv": _CSV}
    # The document this file already uses throughout: one series that reads, and a `rowIndex`
    # source that selects an indexSet, which a conformant document is expected to have.
    assert unreadable_data_descriptions(_document(), files) == ()
    assert read_sedml_data(_document(), files) == {"observedC": (0.0, 4.2, 6.1)}

