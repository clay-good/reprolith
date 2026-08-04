"""Cross-validation: Reprolith reproduces an independent tool's result on diverse real models.

The E. coli core self-validation checks one small model against one documented number. This checks
that ``ingest_fbc_sbml`` + the solver reproduce, on several structurally diverse genome-scale
models (different organisms, 500-750 reactions), the growth rate the community-standard COBRApy
computes for each model's distributed medium. The reference values were produced by COBRApy (a
*different* implementation) and committed to ``reference_growth.json``, so this is a genuine
non-circular reproduction — and it exercises the ingester on far more structural variety than the
single core model, where a stoichiometry-, bound-, or objective-parsing bug would surface as a
disagreement.

Needs the ``engine`` (python-libsbml with fbc) and ``fba`` (scipy) extras — but *not* COBRApy,
which only generated the committed reference. Skips without them.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")
pytest.importorskip("scipy", reason="the 'fba' extra (scipy) is not installed")

from reprolith import ingest_fbc_sbml, solve_objective  # noqa: E402

_DIR = Path(__file__).parent.parent / "datasets" / "constraint_based" / "cross_validation"
_REFERENCE = json.loads((_DIR / "reference_growth.json").read_text(encoding="utf-8"))["models"]


@pytest.mark.parametrize("model_id", sorted(_REFERENCE))
def test_reprolith_reproduces_the_reference_growth(model_id: str) -> None:
    record = _REFERENCE[model_id]
    sbml = gzip.decompress((_DIR / f"{model_id}.xml.gz").read_bytes()).decode("utf-8")
    model = ingest_fbc_sbml(sbml)

    # Ingestion recovered the documented structure, so a parsing error can't hide as a coincidence.
    assert len(model.reaction_ids) == record["reactions"]
    assert len(model.species_ids) == record["metabolites"]

    optimum = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    assert optimum == pytest.approx(record["reference_growth"], rel=1e-5)
