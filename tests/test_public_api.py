"""The package as a third-party library consumer meets it (spec: the public API is the product).

Every previous test drives the CLI, the MCP server, or an internal module directly. These check
what someone who has `pip install`ed Reprolith and imports `reprolith` can actually reach.
"""

from __future__ import annotations

import pytest
import reprolith as R


def test_every_exported_name_resolves() -> None:
    missing = [name for name in R.__all__ if not hasattr(R, name)]
    assert not missing, f"__all__ names nothing can import: {missing}"


def test_a_consumer_can_certify_without_reaching_into_a_private_module() -> None:
    """Four of the six classes' pins were unreachable from the exported surface.

    `certify_logical` is exported and refuses every pin the exported names could build — its error
    even names `solver_pin_for(nodes=...)`, which was not among them. The only way through was to
    hand-write the magic algorithm substring into an `EnginePin`, which the guard accepts, so the
    exported surface's one route to a logical certificate was to fake the pin.
    """
    certificate = R.certify_logical(
        paper=R.PaperIdentity(title="toggle switch", doi="10.1/x"),
        engine_pin=R.logical_solver_pin(),
        claims=[R.LogicalClaim(claim_id="ss", quantity="steady states",
                               rules={"A": "!B", "B": "!A"}, reported={"A": 1, "B": 0},
                               source_location="Fig 1")],
    )
    assert certificate.overall is R.OverallVerdict.REPRODUCED
    for pin in (R.spatial_solver_pin, R.stochastic_solver_pin, R.solver_pin_for):
        assert callable(pin)


def test_the_exact_match_default_is_reportable_not_a_key_error() -> None:
    """`require_documented_default` holds an exact comparison to 0/0 and says so; the public
    accessor raised a bare KeyError for three of the six comparison methods instead."""
    for method in R.ComparisonMethod:
        tolerance = R.default_tolerance(method, R.ReferenceKind.NUMERIC)
        assert tolerance.source is R.ToleranceSource.CLASS_DEFAULT
    exact = R.default_tolerance(R.ComparisonMethod.ATTRACTOR_SET_MATCH, R.ReferenceKind.NUMERIC)
    assert (exact.reproduced_within, exact.partial_within) == (0.0, 0.0)


def test_a_catalog_filter_that_compares_equal_is_honoured() -> None:
    """Annotated `object` and compared with `is`, a filter that compares equal returned nothing —
    a read surface answering "there are none" to a question it did not understand."""
    catalog = R.Catalog()
    catalog.add(R.Identifiers(title="P1", accession="A1"), R.ModelClass.LOGICAL)
    query = R.ReprolithQuery(catalog, R.CertificateLedger())
    assert len(query.list_catalog(model_class=R.ModelClass.LOGICAL)) == 1
    assert len(query.list_catalog(model_class="logical")) == 1
    assert len(query.list_catalog(model_class=R.ModelClass.ODE_PKPD)) == 0


def test_a_blocked_certificate_refuses_a_malformed_missing_input() -> None:
    """`advance_to_outcome` was widened to record every missing input and this was not, so a
    sequence put a *list* inside `gap_report` — declared `tuple[str, ...]` — and it serialized,
    digested, reloaded and rendered with nothing on the honesty path refusing it."""
    from reprolith.run import blocked_certificate

    paper = R.PaperIdentity(title="t", doi="")
    pin = R.EnginePin(engine="e", version="1")
    assert blocked_certificate(paper, pin, reason=["a", "b"]).gap_report == ("a", "b")
    assert blocked_certificate(paper, pin, reason="one").gap_report == ("one",)
    for bad in ([], ("",), [None]):
        with pytest.raises(ValueError, match="at least one non-empty missing input"):
            blocked_certificate(paper, pin, reason=bad)  # type: ignore[arg-type]
