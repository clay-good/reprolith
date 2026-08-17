"""The logical worked example, regenerated and checked byte for byte (roadmap #9).

Ingests the shipped SBML-qual toggle model, re-certifies its two reported steady states through
the shared builder, and asserts the rendered certificate matches the committed artifact — so the
worked example is regenerable from the repository alone. Needs the engine extra (python-libsbml).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the engine extra (python-libsbml) is not installed")

from reprolith import (  # noqa: E402
    LogicalClaim,
    PaperIdentity,
    RunMetadata,
    UpdateScheme,
    Verdict,
    certify_logical,
    ingest_qual_sbml,
    judge_attractor_set,
    render_human,
)
from reprolith.logical import solver_pin  # noqa: E402

_WD = Path(__file__).parent.parent / "datasets" / "logical" / "worked_example"
_TOGGLE_RULES = {"A": "!B", "B": "!A"}


def _certificate() -> str:
    cert = certify_logical(
        paper=PaperIdentity(
            title="Toggle switch — a two-gene mutual-repression circuit", doi="10.0/toggle"
        ),
        # The solver is this package, so the pin names the revision of the code that enumerated
        # these states (see reprolith.pins): a change to the enumerator or the judge moves it, and
        # this artifact has to be regenerated rather than kept under a version that never moves.
        engine_pin=solver_pin(),
        claims=[
            LogicalClaim(claim_id="ss_on", quantity="A-ON steady state", rules=_TOGGLE_RULES,
                         reported={"A": 1, "B": 0}, source_location="Fig 1a"),
            LogicalClaim(claim_id="ss_off", quantity="A-OFF steady state", rules=_TOGGLE_RULES,
                         reported={"A": 0, "B": 1}, source_location="Fig 1b"),
        ],
    )
    run = RunMetadata(
        created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1"
    )
    return render_human(cert, run) + "\n"


def test_worked_example_certificate_regenerates_byte_for_byte() -> None:
    assert _certificate() == (_WD / "certificate.txt").read_text(encoding="utf-8")


def test_shipped_model_ingests_to_the_toggle() -> None:
    net = ingest_qual_sbml((_WD / "model.xml").read_text(encoding="utf-8"))
    assert net.nodes == ("A", "B")
    assert {tuple(sorted(fp.items())) for fp in net.fixed_points()} == {
        (("A", 0), ("B", 1)),
        (("A", 1), ("B", 0)),
    }


def test_attractor_set_claim_is_scheme_sensitive() -> None:
    # The README's teaching point, pinned as a test: reporting only the two fixed points fails
    # synchronously (the 2-cycle is surfaced) but reproduces asynchronously (the cycle is gone).
    net = ingest_qual_sbml((_WD / "model.xml").read_text(encoding="utf-8"))
    reported = [[{"A": 1, "B": 0}], [{"A": 0, "B": 1}]]
    from reprolith import Attribution, FailureMode, Fault

    sync = judge_attractor_set(
        claim_id="att", quantity="attractor set", source_location="Fig 2",
        reported=reported, network=net, scheme=UpdateScheme.SYNCHRONOUS,
        attribution=Attribution(
            mode=FailureMode.UNSPECIFIED_UPDATE_SCHEME, implicated="update scheme",
            fault=Fault.MANUSCRIPT,
        ),
    )
    async_ = judge_attractor_set(
        claim_id="att", quantity="attractor set", source_location="Fig 2",
        reported=reported, network=net, scheme=UpdateScheme.ASYNCHRONOUS,
    )
    assert sync.verdict is Verdict.FAILED
    assert async_.verdict is Verdict.REPRODUCED
