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


def test_a_family_of_entry_points_reaches_the_surface_together() -> None:
    """One sibling exported and the rest not is worse than none: it teaches the wrong pattern.

    `corroborate_curve` was on the surface and the three classes added after it were not, so a
    consumer who found the ODE one and went looking for their own class's would conclude the
    package had none. The same happened one module over on the day `footprint_origins` and its
    note were added beside already-exported siblings.

    Asserted as families rather than as "everything in every module's `__all__`", which would be
    the wrong rule: `cli.main`, the MCP server's internals, and the per-class `solver_pin` names
    that collide are all deliberately not re-exported.
    """
    import reprolith.corroboration as corroboration
    import reprolith.selection as selection

    for module in (corroboration, selection):
        unreachable = [name for name in module.__all__ if not hasattr(R, name)]
        assert not unreachable, (
            f"{module.__name__} declares {unreachable} public and the package does not export "
            "them, while their siblings are on the surface"
        )
    # And the one the selection guide tells a reader to use, which lives in its own module.
    assert callable(R.derive_footprints)

