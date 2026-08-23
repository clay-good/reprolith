"""A pure-Python class's pin moves when its solver does (spec: verification-queue — freshness).

Re-verification is triggered by a certificate's engine pin differing from the current one. For the
four classes whose solver is this package — the SSA, the finite-difference solver, the attractor
enumerator, and the constraint-based analysis layer — the pin's only moving part used to be a
package version that has never been bumped, so a fix to any of those solvers left every certificate
it invalidates comparing equal to the current pin. These tests hold the mechanism that closed that:
each such pin names a revision of the code that computed the result, and the committed certificates
carry the revision they were generated under.

Dependency-free: the revision is a digest of source files, so nothing here needs an extra (not even
the constraint-based one, whose pin's scipy half is deliberately not what these tests check).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    EnginePin,
    RunMetadata,
    certificate_from_content,
    certificates_needing_review,
    render_human,
)
from reprolith.logical import solver_pin as logical_pin
from reprolith.model import OverallVerdict, PaperIdentity
from reprolith.pins import algorithm_revision
from reprolith.spatial import solver_pin as spatial_pin
from reprolith.stochastic import solver_pin as stochastic_pin

_DATASETS = Path(__file__).parent.parent / "datasets"

# Each pure-Python class: where its committed certificates live, and the modules whose source its
# pin's revision spans. The constraint-based class is included: only the scipy half of its pin needs
# the extra, and the revision — the part these tests are about — does not.
_CLASSES = {
    "stochastic": (
        "stochastic/milestone/certificates", ("stochastic", "oracle", "certificate"),
    ),
    "spatial": ("spatial/milestone/certificates", ("spatial", "oracle", "certificate")),
    "logical": ("logical/milestone/certificates", ("logical", "oracle", "certificate")),
    "constraint_based": (
        "constraint_based/milestone/certificates",
        # `sbml` decides which LP is solved for this class — see fba.solver_pin.
        ("fba", "sbml", "constraint_based", "oracle", "certificate"),
    ),
    # The two classes whose *solver* is an external engine still have a Reprolith judge, and a
    # tolerance or verdict-rule change invalidates their certificates exactly as it does the
    # self-solved ones. Their pins carry the judge's revision beside the engine's own version.
    # …and the two Reprolith modules between the solver and the judge: `engine` picks the grid and
    # the species column, `certify` derives the metric. Either can change the number being judged
    # without the solver's version or the verdict rule moving.
    "ode-pkpd": ("milestone/certificates", ("engine", "certify", "oracle", "certificate")),
    "kinetic": (
        "kinetic/milestone/certificates", ("engine", "certify", "oracle", "certificate"),
    ),
}


def test_a_revision_of_nothing_is_refused() -> None:
    # sha256 of no bytes is a well-formed digest, and a pin carrying it would read as the revision
    # of some code rather than of none.
    with pytest.raises(ValueError, match="at least one module"):
        algorithm_revision()


def test_a_revision_is_a_deterministic_digest_of_the_named_sources() -> None:
    first = algorithm_revision("stochastic", "oracle")
    assert first == algorithm_revision("stochastic", "oracle")
    assert len(first) == 12 and all(c in "0123456789abcdef" for c in first)


def test_a_revision_spans_exactly_the_modules_it_names() -> None:
    # The judge is part of the computation, so a class's revision covers its oracle too — which
    # means the solver alone and the solver-plus-oracle are different revisions, and two classes
    # sharing the oracle still differ.
    assert algorithm_revision("stochastic") != algorithm_revision("stochastic", "oracle")
    # And the rule that turns assessments into the headline verdict is in the path too.
    assert (
        algorithm_revision("stochastic", "oracle")
        != algorithm_revision("stochastic", "oracle", "certificate")
    )
    assert algorithm_revision("spatial", "oracle") != algorithm_revision("stochastic", "oracle")
    # Order is part of the identity, so a revision cannot be produced two ways.
    assert algorithm_revision("spatial", "oracle") != algorithm_revision("oracle", "spatial")


def test_every_pure_python_pin_names_its_solver_revision() -> None:
    for pin, modules in (
        (stochastic_pin(), ("stochastic", "oracle", "certificate")),
        (spatial_pin(), ("spatial", "oracle", "certificate")),
        (logical_pin(), ("logical", "oracle", "certificate")),
    ):
        assert pin.algorithm is not None
        assert f"rev {algorithm_revision(*modules)}" in pin.algorithm


def test_a_moved_revision_re_opens_the_certificates_pinned_to_the_old_one() -> None:
    # The property the revision exists for: a certificate generated before a solver change is
    # flagged for re-verification instead of reading as current. An older revision is stood in for
    # by the pin an earlier release actually wrote — the package version with no algorithm at all.
    from reprolith.certificate import build_certificate
    from reprolith.supersession import CertificateLedger

    current = stochastic_pin()
    stale = EnginePin(engine=current.engine, version=current.version, algorithm=None)
    ledger = CertificateLedger()
    for pin in (current, stale):
        cert = build_certificate(
            paper=PaperIdentity(title=f"pinned to {pin.algorithm}", doi=""),
            engine_pin=pin,
            assessments=(),
            assumptions=(),
        )
        assert cert.overall is OverallVerdict.BLOCKED  # no claims: nothing was checked
        ledger.issue(cert)

    needing = certificates_needing_review(ledger, current)
    assert [cert.engine_pin for cert in needing] == [stale]


def test_every_committed_certificate_carries_the_revision_it_was_generated_under() -> None:
    # A published certificate whose solver has moved since must be regenerated, not silently kept:
    # this is what makes the freshness mechanism true of the corpus and not only of the code. If
    # this fails after editing a solver or the oracle, re-run that class's
    # `scripts/run_*_milestone.py` — the run is the point, not the file.
    for class_name, (directory, modules) in _CLASSES.items():
        revision = algorithm_revision(*modules)
        published = sorted((_DATASETS / directory).glob("*.json"))
        # Per class, not a single global floor: one class's directory going empty must not be
        # covered by another's count, or the guard silently stops guarding that class.
        assert published, f"{class_name} publishes no certificates to check"
        for path in published:
            content = json.loads(path.read_text(encoding="utf-8"))
            algorithm = content["engine_pin"]["algorithm"]
            assert algorithm is not None, f"{path} names no algorithm"
            assert f"rev {revision}" in algorithm, (
                f"{path} was generated under an older revision of {class_name}; re-run that "
                f"class's milestone script to re-certify it under the current solver"
            )


# The rendered certificates committed outside a milestone directory, and the class whose revision
# each was generated under. A render is a published surface too — `datasets/worked_examples/`'s
# metformin certificate is the one the README and docs/mcp-server.md send readers to — and the
# JSON-only sweep above could not see it.
# Every render that lives outside a milestone directory: the class whose revision it was generated
# under, and the committed certificate it is the rendering *of*. The certificate path is what makes
# the byte-for-byte check possible for these three — `scripts/render_worked_examples.py` holds the
# same mapping, and the toggle switch is regenerated from its two claims rather than from a file,
# so `tests/test_logical_worked_example.py` byte-checks that one instead.
_RENDERED_ELSEWHERE = {
    "worked_examples": ("ode-pkpd", "milestone/certificates/BIOMD0000001028.json"),
    # These two write their own `certificate.json` beside the render (see
    # scripts/render_worked_examples.py), so the sibling lookup finds them like any milestone
    # render — no special case, and nothing skipped.
    "constraint_based/worked_example": ("constraint_based", None),
    "logical/worked_example": ("logical", None),
}


def test_every_committed_render_names_the_current_revision_too() -> None:
    # The JSON sweep above globs six milestone directories. The metformin render sat outside all of
    # them, so it kept publishing an engine pin with no judge revision while the machine-readable
    # certificate for the same paper carried one. Every render is checked here, and a render this
    # test cannot attribute to a class fails rather than being skipped: that silent skip is the
    # whole defect.
    #
    # Enumerated by *location*, not by the presence of the line under test. Keyed on
    # `"Engine pin:" in text`, a render that lost its pin line removed itself from the gate — so
    # deleting that line and editing the verdict beneath it passed the whole suite. The population
    # a check runs over must not be defined by the thing the check is looking for.
    directories = {
        directory: name for name, (directory, _) in _CLASSES.items()
    } | {directory: name for directory, (name, _) in _RENDERED_ELSEWHERE.items()}
    sources = {directory: source for directory, (_, source) in _RENDERED_ELSEWHERE.items()}

    renders = sorted(
        path for path in _DATASETS.rglob("*.txt") if path.parent != _DATASETS / "fixtures"
    )
    assert renders, "no rendered certificates found to check"
    for path in renders:
        relative = path.relative_to(_DATASETS)
        parent = relative.parent.as_posix()
        class_name = directories.get(parent)
        assert class_name is not None, (
            f"{relative} is a published certificate render in a directory no freshness check "
            "covers; add it to _CLASSES or _RENDERED_ELSEWHERE"
        )
        text = path.read_text(encoding="utf-8")
        pin_lines = [line for line in text.splitlines() if line.startswith("Engine pin:")]
        assert pin_lines, f"{relative} names no engine pin at all; it cannot be checked for freshness"
        revision = algorithm_revision(*_CLASSES[class_name][1])
        assert f"rev {revision}" in pin_lines[0], (
            f"{relative} names no current revision ({pin_lines[0]!r}); re-render it from the "
            f"certificate its class's milestone script produces"
        )
        # …and the render has to be the render *of* that certificate. Checking only the pin line
        # left every other line unpinned: a hand-edited verdict in a committed render passed the
        # gate untouched. This used to be conditional on a sibling JSON beside the render — and the
        # three worked-example renders have none, including the metformin one that produced the
        # original finding, so the check skipped exactly the file it was written for.
        sibling = path.with_suffix(".json")
        source = sibling if sibling.exists() else (
            _DATASETS / sources[parent] if sources.get(parent) else None
        )
        assert source is not None, (
            f"{relative} has no certificate to be compared against; a render with no source cannot "
            "be checked, and skipping it is how a hand-edited verdict went unnoticed"
        )
        assert source.exists(), f"{relative}'s source certificate {source} is missing"
        cert = certificate_from_content(json.loads(source.read_text(encoding="utf-8")))
        run = RunMetadata(created_at="", actor="gate", tool_version="")
        # Trailing-newline policy differs between the milestone writers and the worked-example
        # renderer; what has to match is the certificate's content, not the file's last byte.
        assert text.rstrip("\n") == render_human(cert, run).rstrip("\n"), (
            f"{relative} is not the rendering of {source.relative_to(_DATASETS)}; re-run "
            "scripts/render_worked_examples.py or that class's milestone script"
        )
