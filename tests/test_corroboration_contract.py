"""One contract, six front-ends: what every cross-engine comparison must publish, whatever it compares.

Each class's second engine grew on its own, months apart, and each was reviewed against the class it
serves rather than against its five siblings. That is how two of them drifted: the stochastic
comparison's degenerate branch put a *build string* where the engine identifier goes, so a record
from it would have named an engine called "gillespie-direct-method (rev b4d8d2ffc52b)"; and the
constraint-based one published scipy's version without the revision of Reprolith's own LP code, so a
change to the objective or the bounds left a record byte-identical to one written before it — the
exact staleness the shared helper exists to prevent, in the one front-end of five that did not call
it.

Neither was reachable by reading a class's own tests, and both fall out of putting the six side by
side. This is that comparison, kept: the invariants below hold over every committed record, so a
seventh engine inherits them instead of being reviewed alone.

Reads the committed artifacts, so it needs no extras and no engine.
"""

from __future__ import annotations

import json
import math
import re

from reprolith.mcp_server import milestone_certificate_dirs

#: An engine identifier: a lowercase slug a record is keyed on and a reader scans a column of. Not
#: a sentence, and not a build string — those go in `engine_versions`.
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]*$")

#: The engines that are this package rather than a third party. Their published build has to name
#: a code revision, because their version number does not move when their code does.
_OURS = ("reprolith-", "scipy-linprog")


def _records() -> dict[str, dict]:
    found = {}
    for model_class, directory in milestone_certificate_dirs().items():
        path = directory.parent / "corroboration.json"
        if path.is_file():
            found[model_class] = json.loads(path.read_text(encoding="utf-8"))
    return found


def _rows():
    for model_class, record in _records().items():
        for key, row in record.items():
            yield f"{model_class}/{key}", row


def test_the_matrix_is_not_empty_and_covers_every_published_class() -> None:
    """Otherwise every assertion below is vacuous."""
    records = _records()
    assert set(records) == set(milestone_certificate_dirs())
    assert sum(len(record) for record in records.values()) >= 100


def test_every_row_names_two_engines_by_identifier_and_not_by_build() -> None:
    """`engines` is the key the registry line, the terminal column and the per-class pair check are
    all read from. A build string there is not a different spelling of the engine — it is a
    different engine, appearing and disappearing as the software is upgraded."""
    for where, row in _rows():
        engines = row["engines"]
        assert len(engines) == 2, where
        assert engines[0] != engines[1], where
        for engine in engines:
            assert _IDENTIFIER.match(engine), (where, engine)
            assert "rev " not in engine, (where, engine)


def test_every_row_names_the_build_each_side_ran() -> None:
    """A corroboration bound carries a certificate's weight: it expires when the software that
    produced it changes. A record naming no build cannot be told from a current one."""
    for where, row in _rows():
        versions = row["engine_versions"]
        assert len(versions) == len(row["engines"]), where
        assert all(version for version in versions), where


def test_our_own_side_publishes_a_code_revision_and_not_a_package_version() -> None:
    """The invariant the constraint-based front-end was missing.

    A third-party engine's version moves when its code does. Reprolith's does not — the package
    version has been 0.0.1 throughout — so a record naming it says nothing about which code
    produced the agreement. Every side that *is* this package therefore publishes the revision of
    the code that ran, which is the same string a certificate's freshness check reads.

    `scipy-linprog` counts as ours: the solver is scipy, but the objective, the bounds and the
    sense are this package's, and scipy's version cannot see a change to any of them.
    """
    checked = 0
    for where, row in _rows():
        for engine, version in zip(row["engines"], row["engine_versions"]):
            if not engine.startswith(_OURS):
                continue
            checked += 1
            assert "rev " in version, (where, engine, version)
    assert checked >= 4, "no row has a Reprolith side; this would pass vacuously"


def test_a_published_bound_never_states_better_agreement_than_a_pass_requires() -> None:
    """Every row is a pass, and every pass is at or under the criterion its comparison uses.

    The three comparison kinds are on three scales — a normalized distance, an exact match, and a
    count of standard errors — and the whole reason the kind is recorded is that a number from one
    read on another's scale is nonsense. So the bound is checked against its own kind's ceiling.
    """
    ceilings = {"normalized-distance": 0.02, "exact-match": 0.0, "monte-carlo-agreement": 3.0}
    for where, row in _rows():
        assert row["engine_independent"] is True, where
        kind = row.get("comparison", "normalized-distance")
        assert kind in ceilings, (where, kind)
        assert 0.0 <= float(row["distance_at_most"]) <= ceilings[kind], (where, kind)


def test_a_sampled_comparison_says_what_it_could_not_have_seen() -> None:
    """And a deterministic one does not, because the field would mean nothing there.

    Two ensembles agree at any criterion if they are small enough, so a Monte Carlo row's
    agreement is only worth the bias it could have resolved. A row compared by distance has no
    such number — its two answers are deterministic — and carrying an empty one would invite
    reading the deterministic classes as unmeasured rather than as not needing it.
    """
    sampled = 0
    for where, row in _rows():
        if row.get("comparison") == "monte-carlo-agreement":
            sampled += 1
            assert 0.0 < float(row["resolves_bias_above"]) < 1.0, where
        else:
            assert "resolves_bias_above" not in row, where
    assert sampled, "no sampled comparison is committed; this would pass vacuously"


def test_a_row_published_by_distance_is_a_decade_and_not_a_measurement() -> None:
    """Its leading digits are the two engines' last-place noise amplified, and they move between
    machines. The published value is the decade the raw distance was rounded up to, so a record
    carrying five figures is a measurement nobody reproduces."""
    for where, row in _rows():
        if row.get("comparison", "normalized-distance") != "normalized-distance":
            continue
        bound = float(row["distance_at_most"])
        assert bound > 0.0, where
        # A decade has mantissa exactly one, so its base-10 log is a whole number.
        assert math.log10(bound) == round(math.log10(bound)), (where, bound)
