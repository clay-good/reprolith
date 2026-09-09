"""One value the author has to state is one item, however many claims recorded it.

The fix list's own rule, from the `presubmission-check` spec: one fix that blocks many claims is one
item naming all of them, since repeating it per claim buries the fixes that differ among the rows
that do not. It was applied to the claims and not to the assumptions — and a certificate records an
assumption *per claim that rests on it*. The stochastic noise entry carries
`ssa-sampling-immigration_death_noise-cv` and `-fano`: two ids for one ensemble, whose fix rows come
out identical word for word, so an author read the same instruction twice and had no way to tell
whether it was one thing or two.

It is the distinction the verification queue already draws by keying an item on the *question*
rather than on the assumption's own id — one solver limitation asked by three claims is one item
with three dependents.

Only a byte-identical row collapses. `dose-salt-form` appears twice in this corpus with different
doses in it, and those are two values to state.
"""

from __future__ import annotations

from reprolith.mcp_server import default_data_dir, load_repository

_NOISE = "immigration_death_noise"


def _query():
    query, _catalog = load_repository(default_data_dir(), aggregate=True)
    return query


def test_no_standing_certificate_asks_for_the_same_fix_twice() -> None:
    query = _query()
    repeated = {}
    for digest, _cert in query._ledger.items():  # noqa: SLF001 - the loaded ledger is the corpus
        fixes = query.presubmission(digest)["fix_list"]
        duplicated = [f for i, f in enumerate(fixes) if f in fixes[:i]]
        if duplicated:
            repeated[digest[:12]] = [f["quantity"] for f in duplicated]
    assert repeated == {}, repeated


def test_the_two_ids_for_one_ensemble_are_one_item_that_still_names_both_claims() -> None:
    """Collapsing must not lose which claims rest on it — the roll-up row carries them."""
    query = _query()
    digest = next(
        d for d, cert in query._ledger.items()  # noqa: SLF001
        if any(_NOISE in a.claim_id for a in cert.assessments)
    )
    fixes = query.presubmission(digest)["fix_list"]
    ensembles = [f for f in fixes if f["kind"] == "assumption" and f["claim_id"] is None
                 and "ensemble Reprolith sampled" in (f["quantity"] or "")]
    assert len(ensembles) == 1, ensembles
    (rollup,) = [f for f in fixes if f.get("claims")]
    assert sorted(rollup["claims"]) == [f"{_NOISE}-cv", f"{_NOISE}-fano"]


def test_two_assumptions_that_differ_stay_two_items() -> None:
    """The one-directional half of the rule: a collapse that merged these would hide a value.

    The metformin corpus states two different salt-form corrections under one assumption id, on two
    certificates. Within a certificate, an assumption whose chosen value differs from another's is a
    separate thing for the author to write down.
    """
    query = _query()
    for digest, cert in query._ledger.items():  # noqa: SLF001
        chosen = {(a.description, a.chosen) for a in cert.assumptions
                  if a.load_bearing or a.verification_item}
        items = [f for f in query.presubmission(digest)["fix_list"]
                 if f["kind"] == "assumption" and f["claim_id"] is None and not f.get("claims")]
        assert len(items) == len(chosen), (digest[:12], len(items), len(chosen))
