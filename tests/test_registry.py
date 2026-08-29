"""The committed public registry stays consistent with the milestone certificates (spec: certificate-publication).

Dependency-free guard on the artifact `scripts/build_registry.py` produces: if the committed
`datasets/registry.html` drifts from the six classes' milestone certificates, this fails and the
registry must be rebuilt. Reading JSON needs no extras, so it runs in the core CI job.
"""

from __future__ import annotations

import argparse
import re
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
    # One entry per published certificate, counted from the directories rather than written here:
    # this has moved four times as the corpus grew, and a literal makes each growth a chore.
    published = len(list(_REPO.glob("datasets/**/milestone/certificates/*.json")))
    assert published > 30, published
    assert html.count('class="entry"') == published
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


def test_every_tool_backed_reference_names_the_tool_that_produced_it() -> None:
    """A `source_location` names where the reference VALUE came from, not just which paper.

    The claims dataset says so in as many words: "A claim's reference value comes from the paper
    (cited in `source_location`), not from re-running the model." For twenty of the thirty
    published certificates it did not — the reference was computed by COBRApy, libRoadRunner or
    CANA re-running the same model file, which is what makes the cross-validation non-circular.

    Driven from the datasets that record `reference_tool`, not from sniffing the rendered citation
    for "doi:" or "et al.". That filter exempted the three kinetic entries whose papers are cited
    by author-year model name ("Tyson1991 - Cell Cycle 6 var"), and since they were never counted,
    the count floor did not notice: their attribution could be removed with the whole suite green.
    """
    import json
    from pathlib import Path

    datasets = Path(__file__).parent.parent / "datasets"

    def cited(directory: str, accession: str) -> str:
        content = json.loads(
            (datasets / directory / f"{accession}.json").read_text(encoding="utf-8")
        )
        return " ".join(a["source_location"] for a in content["assessments"])

    expected: dict[tuple[str, str], str] = {}

    kinetic = json.loads((datasets / "kinetic" / "cross_validation.json").read_text("utf-8"))
    for model in kinetic["models"]:
        expected[("kinetic/milestone/certificates", model["id"])] = model["reference_tool"]

    growth = json.loads(
        (datasets / "constraint_based" / "cross_validation" / "reference_growth.json")
        .read_text("utf-8")
    )
    for model_id, record in growth["models"].items():
        expected[("constraint_based/milestone/certificates", model_id)] = record["reference_tool"]

    for name in ("reference", "scalable_fixed_points"):
        logical = json.loads(
            (datasets / "logical" / "cross_validation" / f"{name}.json").read_text("utf-8")
        )
        tool = logical["_source"].split(";")[0].split(":")[0].strip()
        for key in logical["models"]:
            expected[("logical/milestone/certificates", key)] = tool

    # 6 kinetic + 7 genome-scale FBA + 6 CANA logical + 3 SAT logical. An equality, not a
    # floor: a floor cannot notice an entry that was never counted, which is how the
    # previous version of this gate exempted three certificates.
    assert len(expected) == 22, f"the reference datasets describe {len(expected)}, not 22"

    for (directory, accession), tool in sorted(expected.items()):
        text = cited(directory, accession)
        assert "computed by" in text, (
            f"{accession} cites its paper without saying where its reference value came from"
        )
        head = tool.split()[0]
        assert head in text, f"{accession} names no reference tool; expected {tool!r}"


def test_the_registry_tells_an_author_what_they_can_run() -> None:
    """The page publishes verdicts on other people's work, which is no use to the person deciding
    what to ship. What is use to them needs no submission and no certificate — so it says so, and
    says exactly what it is, since a command on a page of certificates must not read as a way to
    obtain one."""
    from reprolith.cli import build_parser

    html = _REGISTRY.read_text(encoding="utf-8")
    assert 'class="authors"' in html
    assert "runs no model" in html
    assert "issues no certificate" in html

    shown = re.findall(r"^reprolith ([a-z][a-z-]*)", html, re.MULTILINE)
    assert shown, "the author section shows no command; this check would pass vacuously"
    parser = build_parser()
    subcommands = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    ).choices
    assert set(shown) <= set(subcommands), f"the registry shows commands that do not exist: {shown}"
