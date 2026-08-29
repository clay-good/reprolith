"""An AUC is a property of the sample grid as well as of the model.

Found by pointing the engine at the mouse intravenous metformin model, whose 24-hour plasma AUC
reads 658, 406, 280, 218, 188 and 174 nmol·h/mL as the sample count doubles from 240 to 7680 — a
bolus profile, integrated by trapezoids. A verdict computed on the first of those is a verdict
about the grid. The same measurement on a smooth oral profile agrees to six figures from 240
samples up, which is why nothing had ever noticed.

The rule is the one the number itself suggests: when the metric's own sampling uncertainty is
wider than the width that separates a pass from a failure, the comparison cannot tell them apart,
so the claim abstains. It can only turn a judgment into an abstention, never the reverse — and no
committed claim uses this metric, so nothing in the corpus moved.

Needs the `engine` extra.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")
pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")

from reprolith import Claim, PaperIdentity, Verdict, certify_model  # noqa: E402
from reprolith.certify import _auc_is_established  # noqa: E402
from reprolith.engine import engine_pin  # noqa: E402

_WORKED = Path(__file__).parent.parent / "datasets" / "worked_examples"
_HUMAN = (_WORKED / "Zake2021_metformin_human_single_PO.xml").read_text(encoding="utf-8")


def test_a_smooth_oral_profile_has_an_established_auc() -> None:
    """The case that must keep working: an ordinary PK curve converges immediately."""
    established, change = _auc_is_established(
        _HUMAN, "mPlasmaVenous", duration=24.0, steps=480, within=0.05
    )
    assert established
    assert change < 1e-4, change


def test_a_claim_on_that_profile_is_judged_as_before() -> None:
    """The guard must be invisible where the number is stable."""
    claim = Claim(
        claim_id="AUC24", quantity="plasma AUC over 24 h", species="mPlasmaVenous",
        reported=42.2, source_location="Table 6, plasma row, 500 mg", metric="auc",
    )
    cert = certify_model(
        _HUMAN, paper=PaperIdentity(title="Zake2021", doi="10.1371/journal.pone.0249594"),
        engine_pin=engine_pin(), claims=[claim], duration=24.0, steps=480,
    )
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.REPRODUCED


def test_an_unconverged_auc_abstains_rather_than_reporting_a_verdict() -> None:
    """A synthetic bolus: everything happens in the first minute of a 24-hour window.

    Synthetic on purpose — the model that exposed this is not in the corpus, and a guard that
    only fires on one downloaded file is a guard nobody can re-run.
    """
    spike = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="bolus">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" initialAmount="1000" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters><parameter id="k" value="500" constant="true"/></listOfParameters>
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
    established, change = _auc_is_established(
        spike, "C", duration=24.0, steps=48, within=0.05
    )
    assert not established and change > 0.05

    claim = Claim(
        claim_id="AUC", quantity="area under the curve", species="C",
        reported=2.0, source_location="Table 1", metric="auc",
    )
    cert = certify_model(
        spike, paper=PaperIdentity(title="synthetic", doi=""), engine_pin=engine_pin(),
        claims=[claim], duration=24.0, steps=48,
    )
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.NOT_EVALUABLE
    assert "property of the grid" in (assessment.root_cause or assessment.discrepancy or "")
    # The run behind the abstention is still recorded, so a reader can re-run it at more samples.
    assert "steps=48" in (assessment.protocol or "")


def test_the_guard_only_applies_to_the_metric_that_needs_it() -> None:
    """A peak and an end value are read off a sample, not integrated over the grid."""
    spike_claim = Claim(
        claim_id="peak", quantity="peak", species="mPlasmaVenous", reported=6.1,
        source_location="Table 6", metric="cmax",
    )
    cert = certify_model(
        _HUMAN, paper=PaperIdentity(title="Zake2021", doi=""), engine_pin=engine_pin(),
        claims=[spike_claim], duration=24.0, steps=480,
    )
    (assessment,) = cert.assessments
    assert assessment.verdict is Verdict.REPRODUCED
