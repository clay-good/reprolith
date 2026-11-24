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
    """Collapsing must not lose which claims rest on it — the roll-up row carries them.

    Built here rather than read off the shipped noise certificate, which no longer carries the
    assumption at all: its ensemble was bought up to the size at which the draw stops being a
    choice the verdict rests on, and a check reading that artifact would now pass by having
    nothing to collapse. The shape it guards is unchanged — two claims, one ensemble, two
    assumption ids whose fix rows come out identical word for word — so it is reproduced on a
    small ensemble, which is where the assumption still belongs.
    """
    import math

    from reprolith import (
        NoiseClaim,
        NoiseStatistic,
        PaperIdentity,
        certify_stochastic,
        presubmission_report,
    )
    from reprolith.stochastic import Reaction, solver_pin

    mean = 10.0
    certificate = certify_stochastic(
        paper=PaperIdentity(title="an immigration-death process"), engine_pin=solver_pin(),
        n_species=1, reactions=[Reaction(mean, (), ((0, 1),)), Reaction(1.0, ((0, 1),), ())],
        initial=[0],
        noises=[
            NoiseClaim(
                claim_id=f"{_NOISE}-fano", quantity="Fano factor", species=0,
                statistic=NoiseStatistic.FANO_FACTOR, reported_value=1.0,
                source_location="closed-form", duration=40.0, trajectories=4000, seed=20260907,
            ),
            NoiseClaim(
                claim_id=f"{_NOISE}-cv", quantity="coefficient of variation", species=0,
                statistic=NoiseStatistic.COEFFICIENT_OF_VARIATION,
                reported_value=1.0 / math.sqrt(mean),
                source_location="closed-form", duration=40.0, trajectories=4000, seed=20260907,
            ),
        ],
    )
    # Two claims, one ensemble, and the assumption recorded once per claim that rests on it.
    assert len(certificate.assumptions) == 2
    fixes = presubmission_report(certificate)["fix_list"]
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
