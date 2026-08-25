"""One archive in, one certificate out (roadmap #4: "a shipped-archive paper flows to a certificate").

This is the whole fast-path walked end to end on the files BioModels actually ships for the
Kholodenko MAPK model: package them as a COMBINE archive, ingest it, adopt the recipe the document
already wrote down, and certify. Nothing about *which* curves to check or *how long* to run is
written here — the archive says both. The only hand-supplied input is the reference each curve is
judged against, which comes from an independent simulator re-running the same model file, because
the document says what to plot and never what the paper's figure showed.

What the certificate ends up saying is the honest answer for this archive: the two curves of
Figure 2A reproduce under the pinned engine, and the two of Figure 2B are `not-evaluable` — the
document runs them on a model it modifies, and an adopted recipe carries no overrides, so there is
nothing to run them against.

This is deliberately a test rather than a thirty-first published certificate. The model is already
certified through the kinetic milestone; publishing a second certificate for the same model, with a
reference computed the same way, would add a row to the registry and no information to the corpus.
What is worth proving is that the *path* runs, and that is what this asserts.

Needs the ``engine`` extra (python-copasi) and the ``corroborate`` extra (libRoadRunner).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from reprolith import (
    CurveClaim,
    PaperIdentity,
    ReferenceKind,
    Verdict,
    certify_curves,
    engine_pin,
    ingest_omex,
    parse_sedml_recipes,
    simulate_with_roadrunner,
)

pytest.importorskip("COPASI", reason="the optional 'engine' extra (python-copasi) is not installed")
pytest.importorskip(
    "roadrunner", reason="the optional 'corroborate' extra (libRoadRunner) is not installed"
)

_KINETIC = Path(__file__).parent.parent / "datasets" / "kinetic"
_SBML = (_KINETIC / "BIOMD0000000010.xml").read_text(encoding="utf-8")
_SEDML = (_KINETIC / "BIOMD0000000010.sedml").read_text(encoding="utf-8")
_SPEC = "http://identifiers.org/combine.specifications/"

_MANIFEST = f"""<?xml version="1.0" encoding="UTF-8"?>
<omexManifest xmlns="{_SPEC}omex-manifest">
  <content location="." format="{_SPEC}omex"/>
  <content location="./manifest.xml" format="{_SPEC}omex-manifest"/>
  <content location="./BIOMD0000000010_url.xml" format="{_SPEC}sbml.level-2.version-4"/>
  <content location="./BIOMD0000000010.sedml" format="{_SPEC}sed-ml.level-1.version-4"
           master="true"/>
</omexManifest>
"""


def _archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.xml", _MANIFEST)
        zf.writestr("BIOMD0000000010_url.xml", _SBML)
        zf.writestr("BIOMD0000000010.sedml", _SEDML)
    return buffer.getvalue()


def test_an_archive_walks_to_a_certificate_without_hand_written_claims() -> None:
    dossier = ingest_omex(_archive(), entry="BIOMD0000000010")
    recipes = {recipe.task_id: recipe for recipe in parse_sedml_recipes(_SEDML)}
    # The document defines two tasks; only the one over the unmodified model is adoptable.
    assert set(recipes) == {"task_fig2a"}

    claims = []
    for claim in dossier.targetable_claims():
        # The claim's conditions name the task it holds under, which is how a curve reaches the
        # recipe that runs it. A claim whose task has no adoptable recipe, or whose plotted
        # quantity is not one the recipe observes, gets no reference — and abstains.
        recipe = next(
            (r for task, r in recipes.items() if f"task '{task}'" in claim.conditions), None
        )
        reference: tuple[float, ...] = ()
        if recipe is not None and claim.quantity in recipe.observables:
            _, reference = simulate_with_roadrunner(
                _SBML, claim.quantity, duration=recipe.duration, steps=recipe.steps
            )
        claims.append(CurveClaim(
            claim_id=claim.id,
            quantity=claim.quantity,
            species=claim.quantity,
            reference=reference,
            # What the claim is judged against, said on the claim itself: a curve an independent
            # simulator computed is numeric, and one with nothing behind it keeps the dossier's
            # figure reference — the document plots it and never says what it showed.
            reference_kind=ReferenceKind.NUMERIC if reference else ReferenceKind.DIGITIZED_FIGURE,
            source_location=(
                f"{claim.source_location} — reference curve computed by libRoadRunner re-running "
                "this model file, not digitized from the paper"
            ),
            duration=recipe.duration if recipe else 0.0,
            steps=recipe.steps if recipe else 0,
        ))

    certificate = certify_curves(
        _SBML,
        paper=PaperIdentity(title="Kholodenko 2000, MAPK cascade (BIOMD0000000010)", doi=""),
        engine_pin=engine_pin(),
        claims=claims,
    )

    by_claim = {a.claim_id: a for a in certificate.assessments}
    assert len(by_claim) == 4
    figure_2a = [a for a in certificate.assessments if a.claim_id.startswith("plot_0")]
    figure_2b = [a for a in certificate.assessments if a.claim_id.startswith("plot_1")]

    # Figure 2A: adopted recipe, run under COPASI, judged against libRoadRunner's trajectory.
    assert [a.verdict for a in figure_2a] == [Verdict.REPRODUCED, Verdict.REPRODUCED]
    assert all("Figure 2A" in a.source_location for a in figure_2a)
    assert all(
        a.protocol == f"duration=9000.0, steps=1000, read=[{a.quantity}] curve" for a in figure_2a
    )

    # Figure 2B: the document runs it on a model it modifies, so there is no recipe to adopt and
    # no reference — an abstention, not a guess.
    assert [a.verdict for a in figure_2b] == [Verdict.NOT_EVALUABLE, Verdict.NOT_EVALUABLE]
    assert all("nothing to compare" in (a.root_cause or "") for a in figure_2b)
    # And each claim line says what it was judged against, so a reader can tell the two apart.
    assert {a.reference_kind for a in figure_2a} == {ReferenceKind.NUMERIC.value}
    assert {a.reference_kind for a in figure_2b} == {ReferenceKind.DIGITIZED_FIGURE.value}

    # The scope flag travels regardless: reproducibility, never correctness.
    assert certificate.content()["scope"]
