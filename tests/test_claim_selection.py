"""Selecting a paper's claims through the dossier, the query surface, the CLI, and MCP.

Pure policy, no engine — these run in the core CI job. The set-level objective itself is tested in
``test_selection.py``; this is about what a *paper's* claims carry into it, and about the honesty
of the surfaces that publish the answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import (
    EMPTY_POOL_NOTE,
    UNCHARACTERIZED_NOTE,
    Dossier,
    DossierClaim,
    Equation,
    Gap,
    GapKind,
    Parameter,
    claim_selection_pool,
    claim_selection_report,
    dossier_from_dict,
)
from reprolith.catalog import Catalog
from reprolith.cli import run
from reprolith.mcp_server import TOOL_DEFINITIONS, dispatch_tool
from reprolith.query import ReprolithQuery
from reprolith.supersession import CertificateLedger


def _claim(claim_id: str, footprint: frozenset[str], *, targetable: bool = True) -> DossierClaim:
    return DossierClaim(
        id=claim_id,
        quantity="plasma concentration",
        conditions="single oral dose",
        source_location=f"Fig {claim_id}",
        targetable=targetable,
        footprint=footprint,
    )


# One paper, five claims. Figure 2's three panels are one absorption/elimination fit at three
# doses; Figure 3 and Table 1 rest on machinery nothing else touches.
_CENTRAL = frozenset({"k_abs", "k_el", "V_central"})
_PAPER = Dossier(
    entry="ACC1",
    state_variables=("gut", "central", "peripheral"),
    equations=(Equation(target="central", expression="-k_el*central", source_location="Eq 1"),),
    parameters=(
        Parameter(name="k_abs", value=1.2, unit="1/h", source_location="Table 1"),
        Parameter(name="k_el", value=0.3, unit="1/h", source_location="Table 1"),
        Parameter(name="V_central", value=12.0, unit="L", source_location="Table 1"),
        Parameter(name="Q_periph", value=2.0, unit="L/h", source_location="Table 1"),
    ),
    claims=(
        _claim("fig2a", _CENTRAL),
        _claim("fig2b", _CENTRAL),
        _claim("fig2c", _CENTRAL),
        _claim("fig3", frozenset({"Q_periph", "peripheral"})),
        _claim("table1", frozenset({"dose_schedule"})),
        _claim("fig1_schematic", frozenset(), targetable=False),
    ),
    gaps=(Gap(element="dose_schedule", kind=GapKind.DOSING, detail="not stated", load_bearing=True),),
)


def test_only_targetable_claims_are_candidates() -> None:
    # A schematic the oracle cannot check is retained in the dossier and is not something a budget
    # can be spent on: offering it would let a selection buy a claim no verdict can come from.
    pool = claim_selection_pool(_PAPER)
    assert [item.id for item in pool] == ["fig2a", "fig2b", "fig2c", "fig3", "table1"]


def test_claims_carry_equal_value_unless_the_caller_says_otherwise() -> None:
    # Reprolith holds no basis for calling one published result more valuable than another, so it
    # does not invent one; under equal values the objective is purely about independence.
    assert {item.value for item in claim_selection_pool(_PAPER)} == {1.0}
    weighted = claim_selection_pool(_PAPER, values={"fig3": 2.0})
    assert {item.id: item.value for item in weighted}["fig3"] == 2.0


def test_a_value_keyed_to_a_claim_that_is_not_there_is_refused() -> None:
    # Silently ignoring it would let a selection be defended by numbers the caller believes were
    # applied and were not.
    with pytest.raises(ValueError, match="no such claim in this dossier: fig9"):
        claim_selection_pool(_PAPER, values={"fig9": 5.0})


def test_the_selection_spreads_across_the_model_where_a_ranking_would_not() -> None:
    report = claim_selection_report(_PAPER, budget=3)
    assert report["selection"]["chosen"] == ["fig2a", "fig3", "table1"]
    assert report["greedy_baseline"]["chosen"] == ["fig2a", "fig2b", "fig2c"]
    assert report["differs_from_greedy"]
    assert len(report["selection"]["covered"]) > len(report["greedy_baseline"]["covered"])
    assert report["limits"] == []


def test_a_footprint_naming_nothing_the_dossier_records_is_reported_not_refused() -> None:
    # An adopt-and-verify dossier keeps its structure in the shipped model file, so a claim there
    # legitimately rests on a reaction the dossier never names. Refusing those would make
    # footprints unusable for most of the catalog — so they are surfaced instead.
    assert _PAPER.unanchored_footprint_elements() == ()
    stranger = Dossier(entry="ACC2", claims=(_claim("c1", frozenset({"reaction_R7"})),))
    assert stranger.unanchored_footprint_elements() == ("reaction_R7",)
    assert stranger.validate() == []
    assert claim_selection_report(stranger, budget=1)["unanchored_footprint_elements"] == [
        "reaction_R7"
    ]


def test_a_selection_over_uncharacterized_claims_says_it_optimized_nothing() -> None:
    # The state of every dossier in the repository today. With no recorded overlap to measure the
    # answer *is* the ranking's, and a report that presented it as an optimized set would be
    # claiming an analysis it did not perform.
    bare = Dossier(
        entry="ACC3",
        claims=(_claim("a", frozenset()), _claim("b", frozenset()), _claim("c", frozenset())),
    )
    report = claim_selection_report(bare, budget=2)
    assert UNCHARACTERIZED_NOTE in report["limits"]
    assert not report["differs_from_greedy"]


def test_a_partly_characterized_paper_says_which_claims_carry_nothing() -> None:
    mixed = Dossier(
        entry="ACC4",
        claims=(_claim("a", _CENTRAL), _claim("b", _CENTRAL), _claim("c", frozenset())),
    )
    report = claim_selection_report(mixed, budget=2)
    assert report["characterized_candidates"] == 2
    assert "2 of 3 candidate claims record a footprint" in report["limits"][0]


def test_a_dossier_with_no_targetable_claim_says_so_rather_than_blaming_the_budget() -> None:
    # Both select nothing and only one of them is fixed by a bigger budget.
    empty = Dossier(entry="ACC5", claims=(_claim("s", frozenset(), targetable=False),))
    assert claim_selection_report(empty, budget=99)["limits"] == [EMPTY_POOL_NOTE]


def test_a_footprint_survives_the_json_round_trip() -> None:
    # A field a writer emits and a reader drops is a dossier that loses what it recorded — the
    # defect shape this package has hit often enough to test for by reflex.
    restored = dossier_from_dict(json.loads(json.dumps(_PAPER.to_dict())))
    assert {c.id: c.footprint for c in restored.claims} == {
        c.id: c.footprint for c in _PAPER.claims
    }


def test_a_claim_with_no_footprint_writes_the_same_bytes_as_before_the_field_existed() -> None:
    # The digest of every dossier already published depends on it.
    plain = DossierClaim(id="c", quantity="q", conditions="x", source_location="Fig 1")
    assert "footprint" not in plain.to_dict()


def test_a_blank_footprint_element_is_refused() -> None:
    with pytest.raises(ValueError, match="a footprint element must name something"):
        DossierClaim(id="c", quantity="q", conditions="x", source_location="Fig 1",
                     footprint=frozenset({"  "}))


def _repo(tmp_path: Path) -> Path:
    """A minimal repository holding one real dossier, as the milestone run writes them."""
    (tmp_path / "catalog.json").write_text(
        json.dumps(Catalog().to_dict(), sort_keys=True), encoding="utf-8"
    )
    (tmp_path / "dossiers").mkdir()
    (tmp_path / "dossiers" / "ACC1.json").write_text(
        json.dumps(_PAPER.to_dict(), sort_keys=True), encoding="utf-8"
    )
    return tmp_path


def test_the_cli_shows_the_chosen_set_and_what_a_ranking_would_have_taken(tmp_path, capsys) -> None:
    assert run(["--data-dir", str(_repo(tmp_path)), "select-claims", "ACC1", "--budget", "3"]) == 0
    out = capsys.readouterr().out
    assert "SELECTED 3 OF 5 TARGETABLE CLAIMS" in out
    # The comparison is the reason to trust the answer, so it is printed, not left to the JSON.
    assert "ranking one at a time would have taken: fig2a, fig2b, fig2c" in out
    assert "plan for what to attempt, not a result" in out


def test_the_cli_refuses_a_budget_that_is_not_a_budget(tmp_path, capsys) -> None:
    assert run(["--data-dir", str(_repo(tmp_path)), "select-claims", "ACC1", "--budget", "0"]) == 1
    assert "budget must be positive" in capsys.readouterr().err


def test_the_cli_says_which_accession_has_no_dossier(tmp_path, capsys) -> None:
    assert run(["--data-dir", str(_repo(tmp_path)), "select-claims", "NOPE", "--budget", "2"]) == 1
    assert "no dossier for accession: NOPE" in capsys.readouterr().err


def test_an_unreadable_stored_dossier_is_a_message_not_a_traceback(tmp_path, capsys) -> None:
    repo = _repo(tmp_path)
    (repo / "dossiers" / "ACC1.json").write_text(json.dumps({"entry": "ACC1"}), encoding="utf-8")
    assert run(["--data-dir", str(repo), "select-claims", "ACC1", "--budget", "2"]) == 1
    assert "cannot be read as a dossier" in capsys.readouterr().err


def test_the_mcp_tool_answers_the_same_thing_the_cli_prints() -> None:
    # Parity between the two surfaces is the repository's central claim about them.
    assert "select_claims" in {tool["name"] for tool in TOOL_DEFINITIONS}
    query = ReprolithQuery(Catalog(), CertificateLedger(), dossiers={"ACC1": _PAPER.to_dict()})
    answer = dispatch_tool(query, "select_claims", {"accession": "ACC1", "budget": 3})
    assert answer["selection"]["chosen"] == ["fig2a", "fig3", "table1"]


def test_the_mcp_tool_refuses_an_absurd_budget() -> None:
    query = ReprolithQuery(Catalog(), CertificateLedger(), dossiers={"ACC1": _PAPER.to_dict()})
    for budget in (0, -1, 1e12):
        with pytest.raises(ValueError, match="budget must be positive"):
            dispatch_tool(query, "select_claims", {"accession": "ACC1", "budget": budget})
