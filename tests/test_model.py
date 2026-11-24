

def test_a_pin_that_names_no_engine_or_version_is_refused() -> None:
    # A bundle carrying an empty pin validated clean while promising anyone could re-run it.
    import pytest
    from reprolith import EnginePin

    for engine, version in (("", "4.46"), ("copasi", ""), ("  ", " ")):
        with pytest.raises(ValueError, match="engine pin"):
            EnginePin(engine=engine, version=version)


def test_an_unattempted_claim_without_an_id_is_refused() -> None:
    """The id is how a reader asks about a claim nobody ran, and nothing was holding it.

    A budgeted certificate lists the claims it chose *against* — deliberately not as assessments
    carrying a spare verdict, because `not-evaluable` means Reprolith ran the claim and established
    nothing, while this one was never run. That distinction is only usable if each entry can be
    named: an anonymous row says a claim was skipped and gives a reader no way to ask which. The
    mutation harness found the refusal deletable with the whole suite green (2026-11-24).
    """
    import pytest
    from reprolith import UnattemptedClaim

    for blank in ("", "   ", "\t"):
        with pytest.raises(ValueError, match="needs an id"):
            UnattemptedClaim(claim_id=blank, quantity="plasma Cmax", source_location="Table 2")
    # And the quantity and source are not a substitute: they describe the claim, not address it.
    named = UnattemptedClaim(claim_id="c3", quantity="plasma Cmax", source_location="Table 2")
    assert named.to_dict()["claim_id"] == "c3"
