"""Cross-engine corroboration, read from the terminal and over MCP — and its absences.

Corroboration answers the question self-validation cannot: agreement with a ground-truth label
says a verdict was right, not that it was the *model's* behaviour rather than one solver's quirk.
It was computed and committed per class, and rendered on the public registry page alone — so the
two surfaces this repository promises parity between ("the terminal view and the agent view can't
disagree") said nothing about it at all.

What these pin is not that the numbers are large. It is that the **absence** of a check travels as
far as the check does, and that two classes counting different things are never added together.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reprolith.cli import build_parser, run
from reprolith.mcp_server import milestone_certificate_dirs, milestone_corroboration_records
from reprolith.query import corroboration_summary

_ROOT = Path(__file__).parent.parent


def test_every_published_class_appears_even_with_no_second_engine() -> None:
    """A class with no record is present and empty, never missing.

    Returning only the classes that have a file would let any reader publish "all corroborated" by
    iterating what happens to be there. Every class carries a record today, so what this holds is
    the *iteration*: the reader is keyed on the published classes rather than on the files that
    happen to exist, which is what makes a class losing its record show up as an empty row instead
    of as one fewer line. The absence rendering itself is exercised below on a constructed record,
    because a repository where nothing is missing cannot exercise it and the day a class does lose
    an engine is the wrong time to find out the path rotted.
    """
    records = milestone_corroboration_records()
    assert set(records) == set(milestone_certificate_dirs())
    assert all(records.values()), sorted(k for k, v in records.items() if not v)


def test_an_empty_committed_record_is_an_absence_and_not_a_vacuous_pass() -> None:
    """A file holding no rows says nothing was re-run. Counted as checked, it would publish a
    class as corroborated on the strength of zero comparisons — `all()` over no rows is true."""
    summary = corroboration_summary({"kinetic": {}, "logical": {}})
    assert summary["by_class"] == {}
    assert summary["unchecked"] == ["kinetic", "logical"]
    assert summary["overall"]["classes_checked"] == 0


def test_claims_and_models_are_never_added_into_one_number() -> None:
    """PK/PD re-runs each claim at its certified dose; the kinetic class re-runs each model once.
    A blended `86` reads as four times what was re-run, so the total keeps the units apart."""
    summary = corroboration_summary(
        {
            "ode-pkpd": {
                "BIOMD1:Cmax": {"engines": ["copasi", "roadrunner"],
                                "engine_independent": True, "distance_at_most": 1e-06},
                "BIOMD1:AUC": {"engines": ["copasi", "roadrunner"],
                               "engine_independent": True, "distance_at_most": 1e-07},
            },
            "kinetic": {
                "BIOMD5": {"engines": ["copasi", "roadrunner"],
                           "engine_independent": True, "distance_at_most": 1e-04},
            },
            "spatial": {},
        }
    )
    assert summary["by_class"]["ode-pkpd"]["unit"] == "claim"
    assert summary["by_class"]["kinetic"]["unit"] == "model"
    assert summary["overall"]["runs"] == {"claim": 2, "model": 1}
    assert summary["overall"]["engine_independent"] == {"claim": 2, "model": 1}
    assert 3 not in summary["overall"]["runs"].values()


def test_the_published_bound_is_the_worst_in_the_class() -> None:
    """A class is only as corroborated as its weakest agreement; publishing the best bound would
    state agreement no claim in it reached."""
    summary = corroboration_summary(
        {"ode-pkpd": {
            "a:1": {"engines": ["copasi"], "engine_independent": True, "distance_at_most": 1e-07},
            "a:2": {"engines": ["copasi"], "engine_independent": True, "distance_at_most": 1e-03},
        }}
    )
    assert summary["by_class"]["ode-pkpd"]["distance_at_most"] == 1e-03


def test_a_class_that_did_not_hold_is_not_summarized_as_holding() -> None:
    summary = corroboration_summary(
        {"ode-pkpd": {
            "a:1": {"engines": ["copasi"], "engine_independent": True, "distance_at_most": 1e-07},
            "a:2": {"engines": ["copasi"], "engine_independent": False, "distance_at_most": 0.4},
        }}
    )
    entry = summary["by_class"]["ode-pkpd"]
    assert (entry["engine_independent"], entry["checked"]) == (1, 2)


def test_a_record_written_before_versions_were_captured_does_not_borrow_todays() -> None:
    """The staleness the engine build exists to make visible.

    A certificate names the software that computed it, and expires when that changes. A
    corroboration bound carries the same weight and named no software at all — a number measured
    against one libRoadRunner read as current against any later build. Filling the gap from the
    installed engines would be worse than leaving it: it would make a stale bound look fresh.
    """
    summary = corroboration_summary(
        {"kinetic": {
            "BIOMD5": {"engines": ["copasi", "roadrunner"],
                       "engine_independent": True, "distance_at_most": 1e-04},
        }}
    )
    assert summary["by_class"]["kinetic"]["engine_versions"] == []


def test_a_class_re_run_across_a_version_change_says_both_builds() -> None:
    """Collapsing them to one would publish a part-stale record as measured on one build."""
    summary = corroboration_summary(
        {"kinetic": {
            "A": {"engines": ["copasi", "roadrunner"], "engine_independent": True,
                  "distance_at_most": 1e-04, "engine_versions": ["4.46", "2.7.0"]},
            "B": {"engines": ["copasi", "roadrunner"], "engine_independent": True,
                  "distance_at_most": 1e-04, "engine_versions": ["4.46", "2.9.0"]},
        }}
    )
    assert summary["by_class"]["kinetic"]["engine_versions"] == [
        "copasi 4.46", "roadrunner 2.7.0", "roadrunner 2.9.0"
    ]


def test_the_committed_records_name_the_builds_they_were_measured_on() -> None:
    """Not that they are any particular version — that they say which."""
    for model_class, record in milestone_corroboration_records().items():
        for key, row in record.items():
            versions = row.get("engine_versions")
            assert versions and all(versions), f"{model_class}/{key} names no engine build"
            assert len(versions) == len(row["engines"])


def test_the_terminal_names_every_published_class(capsys) -> None:
    """Every class prints, with the builds its numbers came out of."""
    assert run(["corroboration"]) == 0
    out = capsys.readouterr().out
    records = milestone_corroboration_records()
    for model_class in records:
        assert model_class in out
    for entry in corroboration_summary(records)["by_class"].values():
        assert ", ".join(entry["engine_versions"]) in out


def test_a_class_that_loses_its_second_engine_prints_as_an_absence() -> None:
    """The path no committed record reaches any more, held on a constructed one.

    Every class carries a record today, so nothing in the repository exercises this — and the
    wording is the whole point of it: a table of only the corroborated classes reads as a
    whole-repository pass. Dropping one class's rows must produce a line saying nothing was
    checked, in the same list as the passes, on both surfaces.
    """
    from reprolith.render import _corroboration_banner

    records = dict(milestone_corroboration_records())
    records["spatial"] = {}
    summary = corroboration_summary(records)
    assert summary["unchecked"] == ["spatial"]
    assert "spatial" not in summary["by_class"]
    banner = _corroboration_banner(records)
    assert "spatial" in banner
    assert "nothing was checked" in banner
    assert "an absence, not a pass" in banner


def test_the_registry_page_and_the_queried_surface_read_one_computation(capsys) -> None:
    """The page is the reason this existed at all, and it must not be able to disagree with the
    surfaces now answering the same question — which it could when it was their only reader."""
    from reprolith.render import _corroboration_banner

    records = milestone_corroboration_records()
    banner = _corroboration_banner(records)
    summary = corroboration_summary(records)
    for model_class, entry in summary["by_class"].items():
        assert f"{model_class}: {entry['checked']} {entry['unit']}(s) re-run" in banner

    assert run(["corroboration", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == summary


def test_the_committed_registry_page_states_what_the_terminal_states(capsys) -> None:
    """Not the shared function — the published bytes. The page in the repository was built by a
    script; nothing until now checked that it said what a reader at a terminal is told today."""
    page = (_ROOT / "datasets" / "registry.html").read_text(encoding="utf-8")
    assert run(["corroboration"]) == 0
    out = capsys.readouterr().out
    summary = corroboration_summary(milestone_corroboration_records())
    for model_class, entry in summary["by_class"].items():
        assert f"{model_class}: {entry['checked']} {entry['unit']}(s) re-run" in page
        assert ", ".join(entry["engine_versions"]) in page
        assert f"{model_class:<18} {entry['checked']:>4} {entry['unit']}(s)" in out
    assert not summary["unchecked"], summary["unchecked"]


def test_the_mcp_tool_and_the_command_are_the_same_answer() -> None:
    """`corroboration` is on the query surface, so both surfaces must expose it. The parity test
    that enumerates every pairing covers the general rule; this one names this tool."""
    from reprolith.mcp_server import TOOL_DEFINITIONS

    assert "corroboration" in {tool["name"] for tool in TOOL_DEFINITIONS}
    subcommands = next(
        a for a in build_parser()._actions if isinstance(a, argparse._SubParsersAction)
    ).choices
    assert "corroboration" in subcommands
