"""Deriving what a claim rests on from the model that produces it.

The measurement selection needed and nothing produced. These hold the two decisions that make the
derived number mean something — the walk's depth, and what it does when it reaches nothing — plus
the rule that keeps a footprint made of names the model actually has.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")

from reprolith.footprints import derive_footprints  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_CLAIMS = json.loads((_ROOT / "datasets" / "pkpd_claims.json").read_text(encoding="utf-8"))
_ENTRY = _CLAIMS["entries"]["BIOMD0000001028"]
_SBML = (_ROOT / "datasets" / _ENTRY["model_file"]).read_text(encoding="utf-8")
_TARGETS = sorted({record["species"] for record in _ENTRY["claims"]})


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def _mean_overlap(depth: int) -> float:
    derived = derive_footprints(_SBML, _TARGETS, depth=depth)
    pairs = [
        _jaccard(derived[a], derived[b]) for a, b in itertools.combinations(_TARGETS, 2)
    ]
    return sum(pairs) / len(pairs)


def test_the_transitive_closure_would_make_every_claim_the_same_claim() -> None:
    """Why the default is a bounded walk, held as a number rather than as a docstring.

    A PBPK model is strongly connected — plasma feeds every tissue and every tissue feeds plasma —
    so the closure from any species is the whole model. Identical footprints overlap completely,
    and a selection over them reports that reproducing any one claim makes every other worthless:
    a statement about the walk, not about the paper.
    """
    closure = derive_footprints(_SBML, _TARGETS, depth=len(_TARGETS) * 8)
    assert len({frozenset(closure[t]) for t in _TARGETS}) == 1, "the closure did discriminate"
    assert _mean_overlap(depth=len(_TARGETS) * 8) == pytest.approx(1.0)


def test_the_default_depth_discriminates_between_tissues_without_collapsing() -> None:
    """The measurement behind `depth=2`: overlap climbs with depth, and 2 is where a claim has
    reached its own machinery and not yet the whole model."""
    assert _mean_overlap(1) < 0.05
    assert 0.1 < _mean_overlap(2) < 0.3
    assert _mean_overlap(3) > _mean_overlap(2)


def test_a_claim_reaches_its_own_tissue_and_the_pool_every_tissue_shares() -> None:
    """What depth 2 actually buys, on elements a reader of this model can name."""
    derived = derive_footprints(_SBML, ["mLiver", "mBrain"])
    assert "Ktp_Liver" in derived["mLiver"] and "Ktp_Liver" not in derived["mBrain"]
    assert "Ktp_Brain" in derived["mBrain"] and "Ktp_Brain" not in derived["mLiver"]
    # The arterial pool and the flow function are machinery every tissue routes through, which is
    # the overlap a selection is spending its budget to avoid buying twice.
    assert {"mPlasmaArterial", "Flow_from_organ"} <= derived["mLiver"] & derived["mBrain"]


def test_a_target_that_reaches_nothing_is_empty_and_never_itself() -> None:
    """The distinction the whole measurement turns on.

    An empty footprint is what selection reads as *not characterized*. A singleton is a
    characterized claim overlapping nothing — so thirty-three views of one model, each carrying
    only its own name, would be reported as thirty-three independent pieces of evidence. That is
    what a walk over the dossier's own equations produced on this corpus, for 77 of its 80 claims.
    """
    minimal = (
        '<?xml version="1.0"?><sbml xmlns="http://www.sbml.org/sbml/level2/version4" '
        'level="2" version="4"><model id="m">'
        '<listOfCompartments><compartment id="c" size="1"/></listOfCompartments>'
        '<listOfParameters><parameter id="alone" value="1"/></listOfParameters>'
        "</model></sbml>"
    )
    derived = derive_footprints(minimal, ["alone", "not_in_this_model"])
    assert derived["alone"] == frozenset()
    assert derived["not_in_this_model"] == frozenset()


def test_only_names_the_model_declares_enter_a_footprint() -> None:
    """A rate law's rendered text carries operators, literals and a called function's bound
    variables. A footprint element must name something the model has, or it cannot be looked up."""
    derived = derive_footprints(_SBML, _TARGETS)
    from reprolith.footprints import _libsbml_vocabulary_for_test  # type: ignore[attr-defined]

    vocabulary = _libsbml_vocabulary_for_test(_SBML)
    for target in _TARGETS:
        assert derived[target] <= vocabulary, target


def test_the_committed_dossiers_carry_the_papers_claims_with_footprints() -> None:
    """Every dossier in this repository recorded zero claims, so `select-claims` had nothing to
    select from anywhere. Held on the artifact, because that is what the surfaces read."""
    dossiers = sorted((_ROOT / "datasets" / "milestone" / "dossiers").glob("*.json"))
    assert dossiers, "no dossiers found; this check would pass vacuously"
    for path in dossiers:
        stored = json.loads(path.read_text(encoding="utf-8"))
        claims = stored["claims"]
        assert claims, f"{path.name} records no claim"
        for claim in claims:
            assert claim["source_location"], claim["id"]
            assert claim.get("footprint"), f"{path.name}/{claim['id']} carries no footprint"
