"""The committed PK/PD milestone artifact, audited as a reader finds it.

The other five classes each have a test that reads their milestone directory back and checks it
says what the class claims. PK/PD — the class carrying the corpus's one manuscript-checked
reproduction — had none. This is that file, and it starts with the artifact that is easiest to let
go stale: the per-claim record of whether a verdict is engine-independent.

Pure stdlib. It re-reads what `scripts/run_milestone.py` wrote; regenerating is what the script is
for, and needs the `engine` and `corroborate` extras.
"""

from __future__ import annotations

import json
from pathlib import Path

_MILESTONE = Path(__file__).parent.parent / "datasets" / "milestone"


def _bundles() -> dict[str, dict]:
    return {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((_MILESTONE / "bundles").glob("*.json"))
    }


def _corroboration() -> dict[str, dict]:
    return json.loads((_MILESTONE / "corroboration.json").read_text(encoding="utf-8"))


def test_every_certified_claim_carries_a_two_engine_result() -> None:
    """A claim with no corroboration entry rests on one solver and nothing says so.

    Keyed off the bundles rather than a hard-coded list, so adding a claim without regenerating
    the artifact fails here instead of shipping a quietly one-engine verdict.
    """
    expected = {
        f"{accession}:{step['claim_id']}"
        for accession, bundle in _bundles().items()
        for step in bundle["recipe"]
    }
    assert expected, "no reconstruction bundle ships a recipe; this audit would pass vacuously"
    assert set(_corroboration()) == expected


def test_each_result_names_both_engines_and_the_arm_it_ran() -> None:
    for key, entry in _corroboration().items():
        assert entry["engines"] == ["copasi", "roadrunner"], key
        assert entry["engine_independent"] is True, key
        # The bound is what is published — see EngineCorroboration.distance_bound — so it is a
        # decade, and it must be at or under the criterion the verdict was held to.
        assert 0 < entry["distance_at_most"] <= 0.01, key


def test_the_recorded_arm_is_the_one_the_claim_was_certified_at() -> None:
    """The overrides are the whole reason this is per claim rather than per model.

    Corroborating both of metformin's claims on the model's default dose would compare the same
    run to itself twice and report engine independence for an arm neither claim uses.

    A claim with a dosing schedule states its own dose in the **last** segment, not in
    `parameter_overrides` — the two are mutually exclusive — so reading the top-level field alone
    said `{}` for a claim that runs at 194.96 mg, and this check would have accepted a
    corroboration of the default arm under that claim's id.
    """
    corroboration = _corroboration()
    for accession, bundle in _bundles().items():
        for step in bundle["recipe"]:
            recorded = corroboration[f"{accession}:{step['claim_id']}"]["overrides"]
            schedule = step.get("schedule") or []
            expected = (
                schedule[-1].get("parameter_overrides", {})
                if schedule
                else step.get("parameter_overrides", {})
            )
            assert recorded == expected, step["claim_id"]
            # And the prior administrations are recorded beside it, so a reader can tell a
            # scheduled run from a single one without going back to the claims dataset.
            assert len(
                corroboration[f"{accession}:{step['claim_id']}"].get("prior_administrations", [])
            ) == max(0, len(schedule) - 1)
    assert any(
        entry["overrides"] for entry in corroboration.values()
    ), "no claim runs at an overridden value, so the override path is untested here"
