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
