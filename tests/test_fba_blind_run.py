"""The constraint-based class closes its blind self-validation loop on the *shared* machinery.

The constraint-based-class spec requires two things this test exercises together: verdicts are
produced blind to the ground-truth label and scored for agreement ("Blind agreement measurement"),
and the class travels the same catalog lifecycle, blind view, and agreement report as PK/PD
("Shared contracts carry the new class"). Here the real E. coli core entry is seeded with its
independently-known label, certified blind through `certify_constraint_based`, then scored and
lifecycle-advanced by the exact `run_test_set` the PK/PD blind run uses — no forked driver.

Needs the ``engine`` (python-libsbml with fbc) and ``fba`` (scipy) extras; skips without them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the 'fba' extra (scipy) is not installed")

from reprolith import (  # noqa: E402
    Catalog,
    DossierClaim,
    EnginePin,
    GroundTruth,
    Identifiers,
    LifecycleState,
    ModelArtifact,
    ModelClass,
    OverallVerdict,
    PaperIdentity,
    Parameter,
    ReferenceKind,
    certify_constraint_based,
    constraint_based_dossier,
    run_test_set,
)
from reprolith.constraint_based import FLUX_UNIT  # noqa: E402

_MODEL_PATH = Path(__file__).parent.parent / "datasets" / "constraint_based" / "e_coli_core.xml"
_ACCESSION = "e_coli_core"
_KNOWN_GROWTH_RATE = 0.873922


def _blind_certificate() -> tuple[Catalog, object]:
    """Seed the labelled entry and produce its certificate without ever consulting the label."""
    catalog = Catalog()
    entry = catalog.add(
        Identifiers(title="E. coli core metabolic model", accession=_ACCESSION),
        ModelClass.CONSTRAINT_BASED,
        ground_truth=GroundTruth(
            expected=OverallVerdict.REPRODUCED,
            source="BiGG / Orth, Fleming & Palsson (2010): known growth rate 0.873922",
        ),
    )
    # The verdict path is handed only the blind view, which has no field for the label at all.
    assert not hasattr(entry.blind(), "ground_truth")

    dossier = constraint_based_dossier(
        _ACCESSION,
        model=ModelArtifact(filename="e_coli_core.xml", detected_format="sbml-fbc", validates=True),
        objective_claims=[DossierClaim(
            id="growth-glucose-aerobic",
            quantity="maximal aerobic growth rate on glucose minimal medium",
            conditions="glucose uptake <= 10 mmol/gDW/h; oxygen unlimited",
            source_location="Orth, Fleming & Palsson (2010); BiGG e_coli_core",
            reference_kind=ReferenceKind.NUMERIC, reference_data=(_KNOWN_GROWTH_RATE,))],
        medium=[
            Parameter(name="R_EX_glc__D_e", value=10.0, unit=FLUX_UNIT,
                      source_location="e_coli_core default medium (BiGG); glucose-limited"),
            Parameter(name="R_EX_o2_e", value=1000.0, unit=FLUX_UNIT,
                      source_location="e_coli_core default medium (BiGG); aerobic"),
        ],
    )
    certificate = certify_constraint_based(
        dossier, sbml=_MODEL_PATH.read_text(encoding="utf-8"),
        paper=PaperIdentity(title="E. coli core", doi="10.1128/ecosalplus.10.2.1"),
        engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="linprog-highs"),
    )
    return catalog, certificate


def test_constraint_based_blind_run_agrees_with_ground_truth() -> None:
    catalog, certificate = _blind_certificate()

    certificates, report = run_test_set(
        catalog.entries, engine_pin=EnginePin(engine="scipy-highs", version="1.13", algorithm="lp"),
        certified={_ACCESSION: certificate}, advance=True,
    )

    # The shared agreement report scores the constraint-based verdict against its label, blind.
    assert report.total == 1
    assert report.agreement_rate() == pytest.approx(1.0)
    assert report.disagreements == ()
    assert certificates[0].overall is OverallVerdict.REPRODUCED

    # The shared lifecycle advanced the constraint-based entry to its outcome, exactly as for PK/PD.
    (entry,) = catalog.entries
    assert entry.state is LifecycleState.CERTIFIED
