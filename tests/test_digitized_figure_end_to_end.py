"""One figure reading in, one certificate out: the claim that could not be judged, judged.

Seven of the ten open-access papers in the seeded PK/PD set state their results in figures, and a
claim whose values live in one abstained permanently — the oracle had the widened tolerance, the
SED-ML document had the claim, and nothing joined them. This walks the whole join: a document that
says which curve is plotted, a curator's digitization of that curve, and a certificate with a real
verdict on it.

Two things are deliberately synthetic, and neither is dressed up. The model is a one-line
exponential decay written here, and the "digitization" is generated from that same decay rather
than read off any published picture — **no published figure is in this corpus**, so the values a
curator would supply have to come from somewhere, and inventing a paper to attribute them to would
be the one thing this repository exists to prevent. What is genuine is the *path*: every stage is
the shipped code, and the reference the certificate is judged against passes through the reader,
the axis scale, and the resampler exactly as a real reading would.

Needs the ``engine`` extra (python-copasi) to run the model.
"""

from __future__ import annotations

import json
import math

import pytest
from reprolith import (
    CurveClaim,
    PaperIdentity,
    ReferenceKind,
    RunMetadata,
    Verdict,
    attach_digitized_values,
    certify_curves,
    engine_pin,
    ingest_sbml,
    parse_sedml_recipes,
    read_digitized_figure,
    render_human,
)

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")

_K = 0.2
_A0 = 8.0

_SBML = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="decay">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialConcentration="8" hasOnlySubstanceUnits="false"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="0.2" constant="true"/></listOfParameters>
    <listOfRules>
      <rateRule variable="A">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><times/><apply><minus/><ci>k</ci></apply><ci>A</ci></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""

_SEDML = """<?xml version="1.0" encoding="UTF-8"?>
<sedML xmlns="http://sed-ml.org/sed-ml/level1/version4" level="1" version="4">
  <listOfModels><model id="m" language="urn:sedml:language:sbml" source="decay.xml"/></listOfModels>
  <listOfSimulations>
    <uniformTimeCourse id="sim" initialTime="0" outputStartTime="0" outputEndTime="24"
                       numberOfSteps="24">
      <algorithm kisaoID="KISAO:0000019"/>
    </uniformTimeCourse>
  </listOfSimulations>
  <listOfTasks><task id="t" modelReference="m" simulationReference="sim"/></listOfTasks>
  <listOfDataGenerators>
    <dataGenerator id="dg_time"><listOfVariables>
      <variable id="v_time" taskReference="t" symbol="urn:sedml:symbol:time"/></listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_time</ci></math></dataGenerator>
    <dataGenerator id="dg_A"><listOfVariables>
      <variable id="v_A" taskReference="t"
                target="/sbml:sbml/sbml:model/sbml:listOfSpecies/sbml:species[@id='A']"/>
      </listOfVariables>
      <math xmlns="http://www.w3.org/1998/Math/MathML"><ci>v_A</ci></math></dataGenerator>
  </listOfDataGenerators>
  <listOfOutputs>
    <plot2D id="plot_0" name="Figure 1">
      <listOfCurves>
        <curve id="c0" logX="false" logY="true" xDataReference="dg_time" yDataReference="dg_A"/>
      </listOfCurves>
    </plot2D>
  </listOfOutputs>
</sedML>
"""


def _digitization(read_at: tuple[float, ...]) -> str:
    """A curator's file for Figure 1, read at the points a human would actually mark."""
    return json.dumps({
        "figure": "Figure 1",
        "digitizer": "WebPlotDigitizer 4.7",
        "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
        "y_axis": {"minimum": 0.01, "maximum": 10, "unit": "nmol/mL", "scale": "log10"},
        "series": [{
            "claim": "c0", "curve": "A",
            "points": [[t, _A0 * math.exp(-_K * t)] for t in read_at],
        }],
    })


def _walk(sbml: str, read_at: tuple[float, ...] = (0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0)):
    """Document -> claim -> the curator's reading -> a certificate, with nothing hand-written."""
    dossier = ingest_sbml(sbml, entry="E1", sedml=_SEDML)
    recipe = parse_sedml_recipes(_SEDML)[0]
    grid = [recipe.duration * i / recipe.steps for i in range(recipe.steps + 1)]

    claims = attach_digitized_values(
        dossier.targetable_claims(), read_digitized_figure(_digitization(read_at)), times=grid,
    )
    return certify_curves(
        sbml,
        paper=PaperIdentity(title="A synthetic decay, with a synthetic figure", doi=""),
        engine_pin=engine_pin(),
        claims=[CurveClaim(
            claim_id=c.id, quantity=c.quantity, species=c.quantity,
            reference=c.reference_data, source_location=c.source_location,
            duration=recipe.duration, steps=recipe.steps, reference_kind=c.reference_kind,
        ) for c in claims],
    )


def test_a_figure_claim_walks_from_a_document_to_a_verdict() -> None:
    """Before this, the same walk ended in `not-evaluable` with no way to supply a value."""
    certificate = _walk(_SBML)
    assessment, = certificate.assessments

    assert assessment.verdict is Verdict.REPRODUCED
    assert assessment.reference_kind == ReferenceKind.DIGITIZED_FIGURE.value
    # The claim came from the document; only the values came from the curator, and the line says
    # both, so a reader of the certificate can see the number was read off a picture.
    assert "SED-ML plot2D 'plot_0' (Figure 1)" in assessment.source_location
    assert "digitized from the figure with WebPlotDigitizer 4.7" in assessment.source_location
    assert assessment.protocol == "duration=24.0, steps=24, read=[A] curve"

    rendered = render_human(
        certificate, RunMetadata(created_at="t", actor="a", tool_version="0.0.1")
    )
    assert "[figure-reading]" in rendered
    assert "tol=reproduced<=0.2, partial<=0.4" in rendered  # the figure band, not 0.1/0.25


def test_the_certificate_is_not_vacuous_on_a_model_the_figure_contradicts() -> None:
    """The same reading against a model decaying a quarter as fast: not a pass, and root-caused.

    Worth stating plainly, because it is the first thing to exercise the widened figure band and
    the band is wide: a model decaying *half* as fast still passes it (normalized distance 0.18
    against a 0.20 budget), because the distance is measured against the reference's own range and
    a decay's disagreement lives in a tail that range dwarfs. The tolerance is documented as
    declared rather than measured, and this is what "declared" buys.
    """
    slower = _SBML.replace('id="k" value="0.2"', 'id="k" value="0.05"')
    assessment, = _walk(slower).assessments

    assert assessment.verdict is Verdict.PARTIAL
    assert assessment.root_cause  # an undiagnosed miss still names the catalogue's escape hatch
    assert assessment.fault_hypothesis


def test_the_axis_the_figure_was_drawn_on_reaches_the_verdict() -> None:
    """Seven readings of a decay are exact on a log axis and 8% wrong read as straight lines.

    The scale an axis is drawn in is not a formatting detail: the same seven points become two
    different reference curves, and the wrong one moves every midpoint by most of the budget a
    printed number is judged in.
    """
    linear = json.loads(_digitization((0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0)))
    linear["y_axis"] = {"minimum": 0, "maximum": 10, "unit": "nmol/mL"}

    dossier = ingest_sbml(_SBML, entry="E1", sedml=_SEDML)
    recipe = parse_sedml_recipes(_SEDML)[0]
    grid = [recipe.duration * i / recipe.steps for i in range(recipe.steps + 1)]
    misread = attach_digitized_values(
        dossier.targetable_claims(), read_digitized_figure(json.dumps(linear)), times=grid,
    )[0]
    faithful = attach_digitized_values(
        dossier.targetable_claims(), read_digitized_figure(_digitization(
            (0.0, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0)
        )), times=grid,
    )[0]

    exact = [_A0 * math.exp(-_K * t) for t in grid]
    assert faithful.reference_data == pytest.approx(exact, rel=1e-9)
    assert misread.reference_data != pytest.approx(exact, rel=1e-3)
    assert max(abs(a - b) / b for a, b in zip(misread.reference_data, exact)) > 0.08
