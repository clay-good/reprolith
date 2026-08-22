"""The committed public registry stays consistent with the milestone certificates (spec: certificate-publication).

Dependency-free guard on the artifact `scripts/build_registry.py` produces: if the committed
`datasets/registry.html` drifts from the six classes' milestone certificates, this fails and the
registry must be rebuilt. Reading JSON needs no extras, so it runs in the core CI job.
"""

from __future__ import annotations

from pathlib import Path

from reprolith import render_registry
from reprolith.mcp_server import milestone_agreement_reports, milestone_certificate_dirs
from reprolith.query import self_validation_summary

_REPO = Path(__file__).parent.parent
_REGISTRY = _REPO / "datasets" / "registry.html"
_SOURCES = milestone_certificate_dirs()


def _collect() -> list:
    """The builder's own collection step, imported rather than re-implemented.

    This guard had its own copy, without the digest de-duplication or the cross-class check the
    builder does — so a duplicated certificate file made the builder correctly publish one card
    while this test demanded two, turning CI red with no rebuild that could fix it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_build_registry", _REPO / "scripts" / "build_registry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collect()


def _rebuild() -> str:
    self_validation = self_validation_summary(milestone_agreement_reports())
    return render_registry(_collect(), self_validation=self_validation)


def test_committed_registry_matches_the_milestone_certificates() -> None:
    assert _REGISTRY.read_text(encoding="utf-8") == _rebuild()


def test_registry_lists_every_class_and_certificate() -> None:
    html = _REGISTRY.read_text(encoding="utf-8")
    assert html.count('class="entry"') == 30  # 1 PK/PD + 8 FBA + 6 kinetic + 9 logical + 3 stochastic + 3 spatial
    for model_class in _SOURCES:
        assert f'data-class="{model_class}"' in html
    # The scope statement travels with the published registry and cannot be emptied.
    assert "clinical" in html.lower()


def test_a_published_card_carries_its_gaps_and_its_stable_identifier() -> None:
    """A qualified result must not be one click away from the reason it was qualified."""
    from reprolith import (
        Assumption,
        ClaimAssessment,
        EnginePin,
        PaperIdentity,
        Verdict,
        build_certificate,
        certificate_digest,
        render_registry,
    )

    cert = build_certificate(
        paper=PaperIdentity(title="A qualified paper", doi="10.1/q"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(
            claim_id="c1", quantity="Cmax", verdict=Verdict.REPRODUCED,
            source_location="Table 1", assumption_qualified=True,
        )],
        assumptions=[Assumption(
            id="a1", description="the salt form of the stated dose", chosen="free base",
            basis="the model's dose input is free base", load_bearing=True,
        )],
    )
    html = render_registry([("ode-pkpd", cert)])
    assert certificate_digest(cert) in html  # addressable by the identifier every surface takes
    assert "what was missing" in html
    assert "the salt form of the stated dose" in html

    # A clean reproduction has nothing missing, so it carries no gap block.
    clean = build_certificate(
        paper=PaperIdentity(title="A clean paper", doi="10.1/c"),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(
            claim_id="c1", quantity="Cmax", verdict=Verdict.REPRODUCED, source_location="Table 1",
        )],
    )
    assert "what was missing" not in render_registry([("ode-pkpd", clean)])


def test_the_builder_refuses_to_publish_a_class_that_is_missing() -> None:
    # A missing directory globs to nothing, so a class whose milestone had not been run simply
    # vanished from the page: exit 0, no warning, and a smaller published track record asserted
    # as the truth (57 labelled entries instead of 60, in the run that found this).
    import importlib.util

    import pytest

    spec = importlib.util.spec_from_file_location(
        "_build_registry_missing", _REPO / "scripts" / "build_registry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._SOURCES = dict(module._SOURCES, spatial=_REPO / "datasets" / "no_such_class")
    with pytest.raises(FileNotFoundError, match="spatial"):
        module.collect()


def test_a_certificate_citing_a_paper_says_where_its_reference_value_came_from() -> None:
    """A `source_location` names where the reference VALUE came from, not just which paper.

    The claims dataset says so in as many words: "A claim's reference value comes from the paper
    (cited in `source_location`), not from re-running the model." For twenty of the thirty
    published certificates it did not — the reference was computed by COBRApy, libRoadRunner or
    CANA re-running the same model file, which is what makes the cross-validation non-circular and
    is the whole point of those sets. Citing only the publication let a certificate read as a
    reproduction of the paper's own published number, over its DOI, when a reader following that
    pointer would find no such number.
    """
    import json
    from pathlib import Path

    datasets = Path(__file__).parent.parent / "datasets"
    tool_backed = {
        "constraint_based/milestone/certificates": "COBRApy",
        "kinetic/milestone/certificates": "libRoadRunner",
        "logical/milestone/certificates": "CANA",
    }
    checked = 0
    for directory, tool in tool_backed.items():
        paths = sorted((datasets / directory).glob("*.json"))
        assert paths, f"{directory} publishes no certificates to check"
        for path in paths:
            content = json.loads(path.read_text(encoding="utf-8"))
            for assessment in content["assessments"]:
                cited = assessment["source_location"]
                # Only the entries that cite a real publication make the claim this guards.
                if "doi:" not in cited and "et al." not in cited:
                    continue
                checked += 1
                assert "reference" in cited and (
                    "computed by" in cited
                ), f"{path.name} cites a publication without saying where its reference came from"
                assert tool in cited or "sympy" in cited, (
                    f"{path.name} names no reference tool; expected {tool}"
                )
    # 19 today: 7 constraint-based (e_coli_core's 0.873922 IS a documented literature
    # value), 6 kinetic, 6 logical. A floor, so the guard cannot quietly stop biting.
    assert checked >= 19, f"only {checked} publication-citing claims found; the guard is not biting"
