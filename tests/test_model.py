

def test_a_pin_that_names_no_engine_or_version_is_refused() -> None:
    # A bundle carrying an empty pin validated clean while promising anyone could re-run it.
    import pytest
    from reprolith import EnginePin

    for engine, version in (("", "4.46"), ("copasi", ""), ("  ", " ")):
        with pytest.raises(ValueError, match="engine pin"):
            EnginePin(engine=engine, version=version)
