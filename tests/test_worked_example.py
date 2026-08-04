"""A real end-to-end reproduction on a published paper (worked example).

Reprolith certifies the Zake2021 metformin PBPK model (BioModels BIOMD0000001028, PLOS ONE
2021, doi:10.1371/journal.pone.0249594) against a claim extracted from the paper: a single
1000 mg oral dose gives a plasma Cmax of 11.2 nmol/mL (Chung dataset). This is a genuine,
non-circular check — the reference value comes from the manuscript, not from re-running the
model — and it reproduces only via a load-bearing salt-form assumption, which is exactly the
kind of under-specification the certificate is built to surface.

Needs the optional ``engine`` extra; skips without it. The model is a CC0 BioModels artifact
under datasets/worked_examples/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("COPASI", reason="the optional 'engine' extra is not installed")
pytest.importorskip("libsbml", reason="the optional 'engine' extra is not installed")

import libsbml  # noqa: E402
from reprolith import (  # noqa: E402
    Assumption,
    Attribution,
    EnginePin,
    FailureMode,
    Fault,
    OverallVerdict,
    PaperIdentity,
    Verdict,
    build_certificate,
    judge_scalar,
    simulate,
)

_MODEL = Path(__file__).parent.parent / "datasets" / "worked_examples" / "Zake2021_metformin_human_single_PO.xml"

# Metformin molar masses: the clinical dose is the HCl salt; the model's dose input is the
# free base. The model's own default (389.92 mg) is 500 mg HCl expressed as free base.
_MW_FREE_BASE = 129.16
_MW_HCL = 165.62
_REPORTED_CMAX = 11.2  # nmol/mL, 1000 mg PO, Chung dataset


def _cmax_at_dose(dose_mg: float) -> float:
    document = libsbml.readSBMLFromString(_MODEL.read_text())
    document.getModel().getParameter("Metformin_Dose_in_Lumen_in_mg").setValue(dose_mg)
    _, values = simulate(libsbml.writeSBMLToString(document), "mPlasmaVenous", duration=24.0, steps=480)
    return max(values)


def test_default_dose_confirms_the_free_base_convention() -> None:
    # The model's default dose is a 500 mg HCl dose expressed as free base.
    assert abs(500.0 * _MW_FREE_BASE / _MW_HCL - 389.92) < 0.1


def test_reproduces_only_with_the_salt_form_assumption() -> None:
    # Taken naively (1000 mg into a free-base input), the model overshoots and fails.
    naive = judge_scalar(
        claim_id="Cmax-1000mg", quantity="plasma Cmax (1000 mg PO)", source_location="Chung dataset, Table/text",
        reported=_REPORTED_CMAX, predicted=_cmax_at_dose(1000.0),
        attribution=Attribution(mode=FailureMode.UNIT_MISMATCH,
                                implicated="oral dose salt form (stated HCl vs model free-base input)",
                                fault=Fault.MANUSCRIPT),
    )
    assert naive.verdict is Verdict.FAILED

    # Applying the load-bearing assumption (1000 mg HCl -> free-base equivalent) reproduces it.
    free_base = 1000.0 * _MW_FREE_BASE / _MW_HCL
    qualified = judge_scalar(
        claim_id="Cmax-1000mg", quantity="plasma Cmax (1000 mg PO)", source_location="Chung dataset, Table/text",
        reported=_REPORTED_CMAX, predicted=_cmax_at_dose(free_base), assumption_qualified=True,
    )
    assert qualified.verdict is Verdict.REPRODUCED
    assert qualified.assumption_qualified


def test_certificate_is_reproduced_but_assumption_qualified() -> None:
    free_base = 1000.0 * _MW_FREE_BASE / _MW_HCL
    assessment = judge_scalar(
        claim_id="Cmax-1000mg", quantity="plasma Cmax (1000 mg PO)", source_location="Chung dataset",
        reported=_REPORTED_CMAX, predicted=_cmax_at_dose(free_base), assumption_qualified=True,
    )
    cert = build_certificate(
        paper=PaperIdentity(title="Zake2021 - PBPK model of metformin in humans, single PO dose",
                            doi="10.1371/journal.pone.0249594"),
        engine_pin=EnginePin(engine="copasi", version="4.46", algorithm="deterministic-lsoda"),
        assessments=[assessment],
        assumptions=[Assumption(
            id="dose-salt-form",
            description="stated 1000 mg oral dose is metformin HCl; the model's dose input is free base",
            chosen=f"{free_base:.1f} mg free base (1000 mg HCl x {_MW_FREE_BASE}/{_MW_HCL})",
            basis="model default 389.92 mg = 500 mg HCl as free base; clinical doses are the HCl salt",
            load_bearing=True,
        )],
    )
    # Every claim reproduced, but it rests on a load-bearing assumption: not a clean pass.
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
