"""Re-fitting a model to the data a paper ships: the deferred half of an estimation reproduction.

The strongest form of reproducibility is not "the shown curve comes out again" but "the *reported
parameter estimates* come out again" (catalog-backlog roadmap #8). The oracle for that landed
first: :func:`reprolith.judge_estimation` compares a reported estimate to a recovered one under a
wider tolerance, and :func:`reprolith.certify_estimation` assembles the certificate. Both took the
recovered estimate as given, because re-running the fit was deferred. This is that half.

A re-fit is sensitive to four things, and an estimate reported without them cannot be repeated —
which is why :class:`reprolith.EstimationClaim` refuses a claim with no protocol, and why
:attr:`EstimationResult.protocol` states all four:

* **The objective.** Ordinary least squares between the observations and the model's trajectory at
  the observation times. Not weighted, not log-transformed: a weighted objective is a modelling
  choice a manuscript has to state, and inventing one changes the answer.
* **The optimizer.** Nelder-Mead, written here rather than imported, with a fixed initial simplex
  and fixed reflection, expansion, contraction, and shrink coefficients — so the same data and
  starting values give the same estimate on every machine, with no dependency whose version could
  move the fourth decimal.
* **The starting values.** The caller's, always. An optimizer's starting point is part of its
  answer for any objective that is not convex, and defaulting it would hide that.
* **The dataset and the grid.** The observations, and the uniform grid the trajectory is computed
  on before being linearly interpolated to the observation times, because a coarse grid biases the
  fit and nothing downstream can see the grid unless it is written down.

Parameters are searched on the **log scale**, so a rate or a volume cannot wander negative and the
search is scale-free — the pharmacometric convention. A fit that does not converge inside its
iteration budget raises rather than returning: an optimizer that stopped early has not produced an
estimate, and publishing one as though it had is the failure this whole path exists to avoid.

Two shapes are refused because they would otherwise publish a fit that did not happen. An
objective that does not move when the parameters do — the parameters are unidentifiable from this
data — because Nelder-Mead on a flat landscape shrinks its simplex until the convergence test
passes and hands back the caller's own starting values as an estimate. And a search that walks off
the log scale entirely, which used to end in an ``OverflowError`` naming nothing.

For the same reason, a parameter region the engine cannot integrate propagates its error rather
than being scored as infinitely bad. Scoring it would be the usual practice and would quietly
steer the search away, leaving no trace that the fit went somewhere the model does not exist —
and the estimate on the other side of that would be reported as though nothing had happened.

Needs the ``engine`` extra: each objective evaluation is a run through :func:`reprolith.simulate`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .engine import simulate

#: Nelder-Mead's standard coefficients: reflection, expansion, contraction, shrink. Named rather
#: than inlined because they are part of the method a protocol claims to have used.
_ALPHA, _GAMMA, _RHO, _SIGMA = 1.0, 2.0, 0.5, 0.5

#: How far the log-scale search may wander before it is called divergent rather than slow. Well
#: inside `math.exp`'s overflow point, so a diverging fit ends with a message that names the
#: parameter instead of an OverflowError that names nothing.
_LOG_LIMIT = 300.0

#: How the initial simplex is built around the starting point, on the log scale: each vertex moves
#: one coordinate by this much. Fixed, so the simplex is a function of the starting values alone.
_SIMPLEX_STEP = 0.1


@dataclass(frozen=True)
class EstimationResult:
    """A re-fit: what it recovered, how well it fit, and the protocol it recovered them under."""

    #: The recovered value per parameter, in the order the parameters were given.
    estimates: tuple[tuple[str, float], ...]
    #: The residual sum of squares at the recovered values.
    objective: float
    iterations: int
    protocol: str

    def value(self, parameter: str) -> float:
        """The recovered estimate for one parameter."""
        for name, estimate in self.estimates:
            if name == parameter:
                return estimate
        raise KeyError(f"{parameter!r} was not among the re-fitted parameters")


def _interpolate(times: tuple[float, ...], values: tuple[float, ...], at: float) -> float:
    """The trajectory at ``at``, linearly interpolated between the two grid points around it."""
    if at <= times[0]:
        return values[0]
    if at >= times[-1]:
        return values[-1]
    # The grid is uniform, so the bracketing index is arithmetic rather than a search.
    span = (times[-1] - times[0]) / (len(times) - 1)
    lower = min(int((at - times[0]) / span), len(times) - 2)
    weight = (at - times[lower]) / (times[lower + 1] - times[lower])
    return values[lower] * (1.0 - weight) + values[lower + 1] * weight


def refit_parameters(
    sbml: str,
    species: str,
    *,
    observations: tuple[tuple[float, float], ...],
    start: tuple[tuple[str, float], ...],
    steps: int = 400,
    max_iterations: int = 400,
    x_tolerance: float = 1e-6,
    f_tolerance: float = 1e-10,
    dataset: str = "the supplied observations",
) -> EstimationResult:
    """Re-fit ``start``'s parameters to ``observations`` by least squares, and report the estimates.

    ``observations`` are ``(time, value)`` pairs of the paper's raw data for ``species``; ``start``
    names each parameter to estimate and the value to start from. The trajectory is computed over
    ``[0, max(time)]`` at ``steps`` intervals and interpolated to the observation times, and the
    objective is their residual sum of squares.

    Every estimated parameter goes through the same override path certification uses, so one the
    model does not declare — or one whose value cannot reach the run — is refused before the fit
    rather than "estimated" by an optimizer moving a number nothing reads.

    Raises ``ValueError`` for a starting value that is not positive (the search is on the log
    scale), for fewer observations than parameters, for an observation at a negative time, and —
    deliberately — when the fit does not converge inside ``max_iterations``. An optimizer that
    stopped early has not produced an estimate.
    """
    from .certify import _apply_overrides  # local: the engine extra is only needed on this path

    if not start:
        raise ValueError("a re-fit must name at least one parameter to estimate")
    names = tuple(name for name, _ in start)
    if len(set(names)) != len(names):
        raise ValueError("each parameter may be estimated once; a repeated name has no meaning")
    bad_start = [name for name, value in start if not (value > 0.0) or not math.isfinite(value)]
    if bad_start:
        raise ValueError(
            "starting values are searched on the log scale and must be positive: "
            + ", ".join(sorted(bad_start))
        )
    if len(observations) < len(start):
        raise ValueError(
            f"{len(observations)} observations cannot identify {len(start)} parameters; a fit "
            "with fewer data points than unknowns returns whichever of infinitely many answers "
            "the optimizer reached first"
        )
    if any(time < 0.0 for time, _ in observations):
        raise ValueError("an observation at a negative time is outside any run this can compute")
    horizon = max(time for time, _ in observations)
    if horizon <= 0.0:
        raise ValueError("every observation is at time zero, so no trajectory is being fitted")
    # Validated once, before the first objective evaluation: an override that cannot reach the run
    # would let the optimizer wander freely over a number nothing reads and report its last guess.
    _apply_overrides(sbml, start)

    def objective(log_values: list[float]) -> float:
        diverged = [
            name for name, value in zip(names, log_values) if abs(value) > _LOG_LIMIT
        ]
        if diverged:
            # Without this the search reaches `math.exp` of a few thousand and the fit ends in an
            # OverflowError naming nothing. A simplex that has walked this far on the log scale —
            # e³⁰⁰ times its starting value — is not converging on an estimate, and saying so is
            # more useful than either an obscure exception or a silent penalty that steers it back.
            raise ValueError(
                "the re-fit diverged: " + ", ".join(sorted(diverged))
                + f" left the range e±{_LOG_LIMIT:g} around a positive value, which is not a "
                "region this model can be run in. Start closer, or check that the parameter is "
                "the one the data identifies."
            )
        overrides = tuple(
            (name, math.exp(value)) for name, value in zip(names, log_values)
        )
        times, trajectory = simulate(
            _apply_overrides(sbml, overrides), species, duration=horizon, steps=steps
        )
        return sum(
            (_interpolate(times, trajectory, time) - observed) ** 2
            for time, observed in observations
        )

    origin = [math.log(value) for _, value in start]
    simplex = [list(origin)] + [
        [value + (_SIMPLEX_STEP if i == j else 0.0) for j, value in enumerate(origin)]
        for i in range(len(origin))
    ]
    scores = [objective(vertex) for vertex in simplex]
    # An objective that does not move when the parameters do is not a fit. Nelder-Mead on a flat
    # landscape shrinks its simplex until the convergence test passes and returns the point it
    # started from, reporting "converged in N iterations" — so an estimate that is nothing but the
    # caller's starting guess reaches the certificate with a protocol saying a fit produced it.
    # Measured on this repository's own model: estimating a parameter the trajectory does not read
    # returned the starting value with a residual sum of squares that never improved.
    if max(scores) - min(scores) <= f_tolerance:
        raise ValueError(
            "the objective does not move when " + ", ".join(names) + " does, so this data does "
            "not identify them: the fit would return the starting values with a residual that "
            "never improved, and reporting that as a recovered estimate is a fit that did not "
            "happen"
        )

    for iteration in range(1, max_iterations + 1):
        order = sorted(range(len(simplex)), key=lambda i: scores[i])
        simplex = [simplex[i] for i in order]
        scores = [scores[i] for i in order]
        if _converged(simplex, scores, x_tolerance, f_tolerance):
            return EstimationResult(
                estimates=tuple(zip(names, (math.exp(v) for v in simplex[0]))),
                objective=scores[0],
                iterations=iteration,
                protocol=(
                    f"ordinary least squares over {dataset} ({len(observations)} observations), "
                    f"Nelder-Mead on the log scale from "
                    + ", ".join(f"{name}={value!r}" for name, value in start)
                    + f"; converged in {iteration} iterations "
                    f"(x_tolerance={x_tolerance!r}, f_tolerance={f_tolerance!r}); trajectory on a "
                    f"uniform grid over [0, {horizon!r}] at {int(steps)} intervals, linearly "
                    f"interpolated to the observation times; read=[{species}]"
                ),
            )
        best, worst = simplex[0], simplex[-1]
        centroid = [
            sum(vertex[i] for vertex in simplex[:-1]) / (len(simplex) - 1)
            for i in range(len(origin))
        ]
        reflected = [c + _ALPHA * (c - w) for c, w in zip(centroid, worst)]
        reflected_score = objective(reflected)
        if scores[0] <= reflected_score < scores[-2]:
            simplex[-1], scores[-1] = reflected, reflected_score
            continue
        if reflected_score < scores[0]:
            expanded = [c + _GAMMA * (r - c) for c, r in zip(centroid, reflected)]
            expanded_score = objective(expanded)
            if expanded_score < reflected_score:
                simplex[-1], scores[-1] = expanded, expanded_score
            else:
                simplex[-1], scores[-1] = reflected, reflected_score
            continue
        contracted = [c + _RHO * (w - c) for c, w in zip(centroid, worst)]
        contracted_score = objective(contracted)
        if contracted_score < scores[-1]:
            simplex[-1], scores[-1] = contracted, contracted_score
            continue
        simplex = [best] + [
            [b + _SIGMA * (v - b) for b, v in zip(best, vertex)] for vertex in simplex[1:]
        ]
        scores = [scores[0]] + [objective(vertex) for vertex in simplex[1:]]

    raise ValueError(
        f"the re-fit did not converge in {max_iterations} iterations (residual sum of squares "
        f"{min(scores):g}); an optimizer that stopped early has not produced an estimate, so "
        "raise max_iterations or start closer rather than publishing where it happened to be"
    )


def _converged(
    simplex: list[list[float]], scores: list[float], x_tolerance: float, f_tolerance: float
) -> bool:
    """Both the vertices and their scores have collapsed — either alone can be met while moving."""
    spread = max(
        abs(vertex[i] - simplex[0][i]) for vertex in simplex[1:] for i in range(len(simplex[0]))
    )
    return spread <= x_tolerance and abs(scores[-1] - scores[0]) <= f_tolerance


__all__ = ["EstimationResult", "refit_parameters"]
