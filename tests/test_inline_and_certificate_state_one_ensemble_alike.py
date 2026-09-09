"""One ensemble, two surfaces, one sentence about what it cost.

The inline linter and the certificate path already share the *abstention* rule, and the reason that
rule gives for being shared is general: whether an ensemble can resolve a claim is a property of the
ensemble and the threshold, not of which surface asked. The same argument reaches a claim the
ensemble **can** resolve, and there the two had diverged — the certificate reported the ensemble's
standard error and the count that would settle the claim, while `lint_stochastic` published a bare
verdict for the identical ensemble at the identical seed.

It reaches those claims harder, in fact. A certificate's reader is a person who can go and look at
the ensemble; a linter's caller is an agent that gates a workflow on the answer and acts on it
immediately. The surface that most needed to say how much of its verdict was sampling noise was the
one that did not.

Needs the `engine` extra to ingest SBML; the SSA itself is pure.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("libsbml", reason="the 'engine' extra (python-libsbml) is not installed")

from reprolith import lint_stochastic  # noqa: E402
from reprolith.stochastic import sampling_cost_clause  # noqa: E402

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "immigration_death.xml"

#: The committed stochastic milestone's own ensemble for this network, so the clause this test
#: compares is the one a published certificate carries rather than a shape invented here.
_ENSEMBLE = {"species": 0, "reported_mean": 10.0, "duration": 40.0, "trajectories": 400,
             "seed": 20260807}


def test_the_linter_reports_what_the_ensemble_cost() -> None:
    result = lint_stochastic(_FIXTURE.read_text(encoding="utf-8"), **_ENSEMBLE)
    assert "sampling noise: the mean's standard error is" in result.protocol
    # And the settling count, which is the half a caller can act on.
    assert "would put the sampling error a tenth of the way to it" in result.protocol


def test_both_surfaces_build_that_sentence_with_one_function() -> None:
    """Not "they agree today" — they cannot disagree, because there is one implementation.

    Checked by driving that implementation with this ensemble's own numbers and finding its output
    verbatim inside what the linter published. A test comparing two independently formatted strings
    would pass until somebody reworded one of them.
    """
    from reprolith.sbml import ingest_stochastic_sbml
    from reprolith.stochastic import ensemble_final_counts, species_mean_variance

    names, reactions, initial = ingest_stochastic_sbml(_FIXTURE.read_text(encoding="utf-8"))
    ensemble = ensemble_final_counts(
        len(names), reactions, initial,
        duration=_ENSEMBLE["duration"], trajectories=_ENSEMBLE["trajectories"],
        seed=_ENSEMBLE["seed"],
    )
    mean, variance = species_mean_variance(ensemble, _ENSEMBLE["species"])
    clause = sampling_cost_clause(
        reported=_ENSEMBLE["reported_mean"], variance=variance,
        trajectories=_ENSEMBLE["trajectories"], observed=mean,
    )
    assert clause
    assert lint_stochastic(_FIXTURE.read_text(encoding="utf-8"), **_ENSEMBLE).protocol.endswith(
        clause
    )


def test_an_ensemble_clear_of_both_lines_is_told_nothing() -> None:
    """The rule the certificate path holds to, on this surface too: a settling count offered to a
    caller who does not need one is noise dressed as advice."""
    clause = sampling_cost_clause(reported=10.0, variance=0.01, trajectories=4000, observed=10.0)
    assert "sampling noise" in clause
    assert "would put the sampling error" not in clause


# --- the same differential, one class over --------------------------------------------------------


def test_the_spatial_linter_reports_the_whole_wall_check_it_gated_on() -> None:
    """The milder form of the same divergence, and the one worth naming separately.

    `unbounded_is_honoured` holds an unbounded claim to two conditions — the wall's bracket under a
    tenth of the pass width, *and* under a tenth of the claim's own distance to its nearest verdict
    line — and both surfaces gate on its `honoured` flag, so the rule never diverged. What diverged
    was the account of it: the certificate's protocol names both thresholds, the linter's named the
    budget alone, and an agent reading that protocol was told a weaker thing had been verified than
    had been.

    Fixed by calling the certificate's own sentence rather than writing a shorter one, so a reworded
    threshold cannot reach one surface and not the other.
    """
    from reprolith.linter import lint_diffusion
    from reprolith.spatial import unbounded_note

    dx, diffusivity = 0.2, 1.0
    dt = 0.008
    steps = 100
    initial = [
        (1.0 / (0.5 * (2.0 * 3.141592653589793) ** 0.5))
        * pow(2.718281828459045, -((i * dx - 10.0) ** 2) / (2 * 0.5**2))
        for i in range(101)
    ]
    # The reference is this solver's own run, so the claim reproduces and the wall clause is the
    # part under test rather than the verdict.
    from reprolith.spatial import diffuse_1d

    reference = diffuse_1d(
        initial, diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, boundary="no-flux"
    )
    result = lint_diffusion(
        initial, reference, diffusivity=diffusivity, dx=dx, dt=dt, steps=steps, boundary="unbounded",
    )
    assert "verified rather than assumed" in result.protocol
    # Both thresholds, which is what the certificate says and what the gate actually checked.
    assert "separates a pass from a failure" in result.protocol
    assert "from the nearest verdict line" in result.protocol
    # And it is the shared sentence, not a paraphrase that happens to contain those words.
    assert unbounded_note.__doc__ is not None
    assert result.protocol.endswith(")")
