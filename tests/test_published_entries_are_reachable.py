"""An accession from any class resolves, not only from the one the work queue holds.

The aggregated read surface loads six classes' *certificates* into one ledger and one class's
*entries* into the catalog. That asymmetry had a consequence nobody had followed: `status` and
`certificates-for` resolve an accession through the catalog — a certificate is keyed by the paper's
title, doi and pubmed id and carries no accession — so an accession from the other five classes came
back "unknown paper", for entries with published, browsable certificates.

The README sends a reader down exactly that path: "`certificates-for` takes
`--by title|doi|pubmed-id|accession`, and it is how you reach the classes the catalog does not
list". Three of those four worked.

The published entries are searched as a **fallback** and are not merged into the catalog. That
catalog is the work queue the effectful surface leases from and every backlog count is over it;
merging sixty-six finished entries into thirty-one queued ones would change every published count
and offer a certified milestone entry to an agent asking for something to do.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from reprolith.catalog import Catalog, Identifiers, ModelClass
from reprolith.cli import run
from reprolith.mcp_server import default_data_dir, load_repository
from reprolith.query import ReprolithQuery
from reprolith.supersession import CertificateLedger

_ROOT = Path(__file__).parent.parent

# One from each class the work queue does not list, with the class it belongs to.
_ELSEWHERE = [
    ("front_speed", "spatial"),
    ("gradient_length", "spatial"),
]


def _aggregated() -> ReprolithQuery:
    query, _catalog = load_repository(default_data_dir(), aggregate=True)
    return query


@pytest.mark.parametrize(("accession", "model_class"), _ELSEWHERE)
def test_an_accession_from_another_class_resolves(accession, model_class) -> None:
    view = _aggregated().status(accession=accession)
    assert view is not None, accession
    assert view["model_class"] == model_class
    # And it reaches the thing the reader wanted: the certificate, not just the entry.
    assert view["certificates"], view


@pytest.mark.parametrize(("accession", "_class"), _ELSEWHERE)
def test_certificates_for_follows_the_route_the_front_page_documents(accession, _class) -> None:
    digests = _aggregated().certificates_for(accession=accession)
    assert len(digests) == 1, digests
    # The same answer the title route already gave — the two must not disagree about one entry.
    query = _aggregated()
    title = query.status(accession=accession)["identifiers"]["title"]
    assert query.certificates_for(title=title) == digests


def test_every_published_class_carries_a_catalog() -> None:
    """The loader raises for a class whose entries are missing, as it does for its track record.

    A class that lost its catalog would go on publishing certificates while every one of its
    entries answered "unknown paper" — the state this file exists about, restricted to one class
    and therefore harder to see.
    """
    from reprolith.mcp_server import milestone_catalogs

    catalogs = milestone_catalogs()
    assert set(catalogs) == {
        "ode-pkpd", "constraint-based", "kinetic", "logical", "stochastic", "spatial",
    }
    assert sum(len(c) for c in catalogs.values()) == 66


def test_the_work_queue_is_not_grown_by_the_published_entries() -> None:
    """The counts every other surface publishes are over the work queue and must not move."""
    query, catalog = load_repository(default_data_dir(), aggregate=True)
    assert len(catalog) == 31
    assert query.backlog_health()["total"] == 31
    assert len(query.list_catalog()) == 31
    assert query.published_entry_count() == 66


def test_the_working_entry_wins_where_both_hold_one() -> None:
    """An entry being worked on is the live record; a milestone copy was taken when it certified.

    Resolving to the snapshot would report a stale lifecycle state for the one class that has both.
    """
    working = Catalog()
    working.add(Identifiers(title="P", accession="A1"), model_class=ModelClass.ODE_PKPD)
    snapshot = Catalog()
    snapshot.add(Identifiers(title="P", accession="A1"), model_class=ModelClass.ODE_PKPD)
    snapshot.entries[0].transition(
        "ingesting", at="2026-01-01T00:00:00Z", actor="milestone", reason="blind run"
    )
    query = ReprolithQuery(
        working, CertificateLedger(), published_catalogs={"ode-pkpd": snapshot}
    )
    assert query.status(accession="A1")["state"] == "queued"


def test_a_repository_with_no_published_catalogs_loaded_says_nothing_extra(capsys) -> None:
    """`--data-dir` loads one directory and no aggregate; the fallback then never fires and the
    listing must not claim a published population it cannot see."""
    assert run(["--data-dir", str(_ROOT / "datasets" / "spatial" / "milestone"), "catalog"]) == 0
    out = capsys.readouterr().out
    assert "5 entries" in out and "this is the work queue" not in out


def test_the_listing_says_what_it_is_not_showing(capsys) -> None:
    assert run(["catalog"]) == 0
    assert "66 entries are published across every class" in capsys.readouterr().out


def test_an_empty_filter_still_says_where_that_class_lives(capsys) -> None:
    """The worst case for silence: five spatial certificates are on the public page, and
    `catalog --model-class spatial` answered "(no matching catalog entries)"."""
    assert run(["catalog", "--model-class", "spatial"]) == 0
    out = capsys.readouterr().out
    assert "(no matching catalog entries)" in out
    assert "66 entries are published across every class" in out
