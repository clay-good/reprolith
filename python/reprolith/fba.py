"""Constraint-based (FBA) reproduction: the optimization oracle (spec: constraint-based-class).

Flux-balance analysis checks a different kind of claim than the PK/PD curve oracle: not "does
the model regenerate a time course" but "does the model's optimization reproduce the reported
outcome" — the objective value under a steady-state, capacity-constrained network. This module
adds only that new comparison method; it reuses the shared contracts, returning the same
:class:`~reprolith.model.ClaimAssessment` the certificate consumes, judged with the same oracle.

The objective value is well-defined even when the flux distribution that achieves it is not
(alternate optima), so an objective-value claim is reproduced or not without guessing among
equivalent flux vectors. Solving the linear program uses the optional ``fba`` extra (scipy);
it is imported lazily, so the core stays dependency-free.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, Union

from .model import ClaimAssessment
from .oracle import (
    Attribution,
    ComparisonMethod,
    ReferenceKind,
    Tolerance,
    assess_match,
    judge_scalar,
    not_evaluable,
)

# A gene–protein–reaction rule: either a single gene label, or a boolean node — a
# ``("and", (child, ...))`` / ``("or", (child, ...))`` tuple — over sub-rules. This is the exact
# structure an SBML-fbc ``geneProductAssociation`` encodes, kept as plain hashable tuples so an
# :class:`FbaModel` stays frozen and comparable.
GprExpr = Union[str, tuple[str, tuple["GprExpr", ...]]]


def _gpr_holds(expr: GprExpr, present: frozenset[str]) -> bool:
    """Whether a GPR rule is satisfied when only the genes in ``present`` are active."""
    if isinstance(expr, str):
        return expr in present
    operator, children = expr
    if operator == "and":
        return all(_gpr_holds(child, present) for child in children)
    return any(_gpr_holds(child, present) for child in children)


def _genes_in(expr: GprExpr) -> set[str]:
    """Every gene label appearing in a GPR rule."""
    if isinstance(expr, str):
        return {expr}
    _, children = expr
    genes: set[str] = set()
    for child in children:
        genes |= _genes_in(child)
    return genes


@dataclass(frozen=True)
class FbaModel:
    """A constraint-based model in the form the oracle solves: the S matrix, the objective, the
    per-reaction flux bounds, and the species/reaction ids that give each row and column a name.

    This is what SBML-fbc ingestion produces (:func:`reprolith.ingest_fbc_sbml`), so a published
    model can be fed straight to :func:`solve_objective`, :func:`flux_variability`, and the judges.
    ``gene_associations`` carries the gene–protein–reaction rule for each reaction that has one
    (``(reaction_id, rule)`` pairs), which is what makes gene-level deletion possible; a model
    ingested without gene data simply has none.
    """

    species_ids: tuple[str, ...]
    reaction_ids: tuple[str, ...]
    stoichiometry: tuple[tuple[float, ...], ...]
    objective: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float | None, ...]
    gene_associations: tuple[tuple[str, GprExpr], ...] = ()

    def reaction_index(self, reaction_id: str) -> int:
        """The column index of a reaction id, for judging that reaction's flux by name."""
        return self.reaction_ids.index(reaction_id)

    def genes(self) -> tuple[str, ...]:
        """Every gene the model's GPR rules mention, in a deterministic order."""
        genes: set[str] = set()
        for _, rule in self.gene_associations:
            genes |= _genes_in(rule)
        return tuple(sorted(genes))


class FbaUnavailable(RuntimeError):
    """Raised when an FBA is requested but the optional ``fba`` extra (scipy) is not installed."""


class InfeasibleFba(RuntimeError):
    """Raised when the flux-balance problem has no bounded, feasible optimum."""


def _linprog() -> Any:
    try:
        from scipy.optimize import linprog
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise FbaUnavailable(
            "constraint-based reproduction needs the 'fba' extra (scipy); "
            "install with pip install 'reprolith[fba]'"
        ) from exc
    return linprog


def _milp() -> Any:
    try:
        from scipy.optimize import milp
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise FbaUnavailable(
            "loopless flux-variability needs the 'fba' extra (scipy); "
            "install with pip install 'reprolith[fba]'"
        ) from exc
    return milp


def solve_objective(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
) -> float:
    """Maximize the objective flux subject to steady state and reaction bounds.

    ``stoichiometry`` is the S matrix (one row per metabolite, one column per reaction);
    ``objective`` weights the reactions in the objective; ``lower``/``upper`` are per-reaction
    flux bounds (``None`` upper for unbounded). Returns the optimal objective value, or raises
    :class:`InfeasibleFba` if the problem is infeasible or unbounded.
    """
    linprog = _linprog()
    result = linprog(
        c=[-x for x in objective],  # linprog minimizes; FBA maximizes
        A_eq=[list(row) for row in stoichiometry],
        b_eq=[0.0] * len(stoichiometry),
        bounds=list(zip(lower, upper)),
        method="highs",
    )
    if not result.success:
        raise InfeasibleFba(f"the flux-balance problem is not solvable: {result.message}")
    return float(-result.fun)


@dataclass(frozen=True)
class ShadowPrices:
    """The LP dual of a flux-balance optimum: the marginal value of each constraint.

    ``metabolites`` gives each metabolite's *shadow price* — the change in the optimum per unit of
    net production imposed on that metabolite's mass balance (∂Z*/∂b). ``reactions`` gives each
    reaction's *reduced cost* — the change in the optimum per unit relaxation of its active flux
    bound (∂Z*/∂bound), and is zero for any reaction not sitting at a bound (complementary
    slackness). Together they are the economic reading of the solution the FROG primal never
    exposes: what each metabolite and each capacity limit is worth to the objective at the optimum.
    Indices follow the metabolite (S-row) and reaction (S-column) order of the inputs.
    """

    metabolites: tuple[float, ...]
    reactions: tuple[float, ...]


def shadow_prices(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
) -> ShadowPrices:
    """Solve the flux-balance LP and return its dual — metabolite shadow prices and reduced costs.

    Same maximization problem as :func:`solve_objective`, read from the other side: the dual
    variables on the steady-state constraints (metabolite shadow prices) and on the reaction bounds
    (reduced costs), both expressed as sensitivities of the *maximized* objective. Raises
    :class:`InfeasibleFba` if the problem is not solvable. Needs the ``fba`` extra (scipy).
    """
    linprog = _linprog()
    result = linprog(
        c=[-x for x in objective],  # linprog minimizes -Z; the duals below are re-signed to Z
        A_eq=[list(row) for row in stoichiometry],
        b_eq=[0.0] * len(stoichiometry),
        bounds=list(zip(lower, upper)),
        method="highs",
    )
    if not result.success:
        raise InfeasibleFba(f"the flux-balance problem is not solvable: {result.message}")
    # scipy reports marginals for the minimization it solved; negate to sensitivities of the
    # maximized objective. A reaction rests on at most one bound, so summing the lower/upper
    # marginals selects whichever is active (the other is zero).
    metabolites = tuple(-float(m) for m in result.eqlin.marginals)
    reactions = tuple(
        -float(lo + up)
        for lo, up in zip(result.lower.marginals, result.upper.marginals)
    )
    return ShadowPrices(metabolites=metabolites, reactions=reactions)


def judge_objective(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: float,
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Reproduce an FBA objective-value claim: solve the LP and judge it against the reported value.

    Uses the oracle's scalar comparison and honesty invariants, so a partial or failed verdict
    still requires an attribution and a load-bearing assumption still qualifies the result.
    """
    predicted = solve_objective(stoichiometry, objective, lower, upper)
    return judge_scalar(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        reported=reported,
        predicted=predicted,
        reference_kind=reference_kind,
        tolerance=tolerance,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


def reaction_essentiality(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    threshold: float = 1e-6,
) -> frozenset[int]:
    """The indices of reactions whose knockout collapses the objective — the essential set.

    A reaction is essential if constraining its flux to zero drops the optimum below
    ``threshold`` of the unperturbed optimum (or makes the problem infeasible). This is the
    second FBA fingerprint the spec names (spec: constraint-based-class), and it too is
    well-defined regardless of alternate optima.
    """
    baseline = solve_objective(stoichiometry, objective, lower, upper)
    if baseline <= 0.0:
        return frozenset()
    essential: set[int] = set()
    for i in range(len(objective)):
        knocked_lower = [0.0 if j == i else lo for j, lo in enumerate(lower)]
        knocked_upper: list[float | None] = [0.0 if j == i else up for j, up in enumerate(upper)]
        try:
            optimum = solve_objective(stoichiometry, objective, knocked_lower, knocked_upper)
        except InfeasibleFba:
            optimum = 0.0
        if optimum < threshold * baseline:
            essential.add(i)
    return frozenset(essential)


def _objective_with_knockouts(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    knockouts: frozenset[int],
) -> float:
    """The optimum after forcing every reaction in ``knockouts`` to zero flux; 0.0 if infeasible."""
    knocked_lower = [0.0 if j in knockouts else lo for j, lo in enumerate(lower)]
    knocked_upper: list[float | None] = [0.0 if j in knockouts else up for j, up in enumerate(upper)]
    try:
        return solve_objective(stoichiometry, objective, knocked_lower, knocked_upper)
    except InfeasibleFba:
        return 0.0


def synthetic_lethal_reactions(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    threshold: float = 1e-6,
    reactions: Sequence[int] | None = None,
) -> frozenset[frozenset[int]]:
    """Reaction pairs that are viable to delete singly but lethal together — the synthetic lethals.

    Double-deletion (epistasis) analysis, the pairwise counterpart of :func:`reaction_essentiality`.
    A pair ``{i, j}`` is synthetic-lethal when neither reaction is essential on its own — each single
    knockout keeps the optimum at or above ``threshold`` of the unperturbed optimum — yet knocking
    out both drops it below that floor (or makes the model infeasible). Single-deletion analysis is
    blind to these: two reactions that back each other up (a redundant or parallel pathway) each look
    dispensable alone, and only the double knockout exposes the dependency.

    ``reactions`` optionally restricts the search to a subset of reaction indices — all pairs drawn
    from it — the way :func:`loopless_flux_variability` accepts a subset; double deletion is O(R²) LP
    solves, so a genome-scale sweep is bounded by naming the reactions of interest. Essential
    reactions in the set are skipped as pair members (their lethality is not synthetic). Returns a set
    of two-element frozensets, so ``{i, j}`` and ``{j, i}`` are one entry.
    """
    baseline = solve_objective(stoichiometry, objective, lower, upper)
    if baseline <= 0.0:
        return frozenset()
    floor = threshold * baseline
    candidates = range(len(objective)) if reactions is None else sorted(set(reactions))
    # Only reactions that are individually viable can form a *synthetic* lethal pair; an essential
    # one makes every pair it joins lethal by itself, which is single-deletion knowledge already.
    viable = [
        i
        for i in candidates
        if _objective_with_knockouts(stoichiometry, objective, lower, upper, frozenset((i,))) >= floor
    ]
    lethal: set[frozenset[int]] = set()
    for a_index in range(len(viable)):
        for b_index in range(a_index + 1, len(viable)):
            pair = frozenset((viable[a_index], viable[b_index]))
            if _objective_with_knockouts(stoichiometry, objective, lower, upper, pair) < floor:
                lethal.add(pair)
    return frozenset(lethal)


def _objective_without_gene(model: FbaModel, gene: str) -> float:
    """The optimum after deleting one gene: every reaction whose GPR then fails is forced to zero.

    A reaction with no GPR (a spontaneous or exchange reaction) is never affected by a gene
    deletion, so only genetically-controlled reactions can be knocked out. Returns 0.0 if the
    knockout makes the model infeasible.
    """
    present = frozenset(g for g in model.genes() if g != gene)
    rules = dict(model.gene_associations)
    lower = list(model.lower)
    upper: list[float | None] = list(model.upper)
    for j, reaction_id in enumerate(model.reaction_ids):
        rule = rules.get(reaction_id)
        if rule is not None and not _gpr_holds(rule, present):
            lower[j] = 0.0
            upper[j] = 0.0
    try:
        return solve_objective(model.stoichiometry, model.objective, lower, upper)
    except InfeasibleFba:
        return 0.0


def gene_essentiality(model: FbaModel, *, threshold: float = 1e-6) -> frozenset[str]:
    """The genes whose deletion collapses the objective — the essential-gene set.

    A gene is essential if deleting it (and forcing to zero every reaction whose gene–protein–
    reaction rule then fails) drops the optimum below ``threshold`` of the unperturbed optimum, or
    makes the model infeasible. This is the gene-level counterpart of :func:`reaction_essentiality`
    and the systematic gene-deletion analysis the spec names (spec: constraint-based-class); it
    reads the GPR rules :func:`reprolith.ingest_fbc_sbml` captures, so it needs no extra input.
    """
    baseline = solve_objective(model.stoichiometry, model.objective, model.lower, model.upper)
    if baseline <= 0.0:
        return frozenset()
    return frozenset(
        gene for gene in model.genes() if _objective_without_gene(model, gene) < threshold * baseline
    )


def flux_variability(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    fraction_of_optimum: float = 1.0,
) -> list[tuple[float, float]]:
    """The min and max each reaction's flux can take while the objective stays optimal.

    This is the honest answer to the alternate-optima problem the spec names (spec:
    constraint-based-class): a single optimal flux vector is ambiguous when many achieve the
    same objective, so instead of picking one, FVA reports the whole feasible interval per
    reaction at (a ``fraction_of_optimum`` of) the optimum. A reaction pinned to a single value
    reproduces exactly; one with a wide interval cannot be certified to a single reported flux.

    Returns one ``(min, max)`` tuple per reaction, in reaction order.
    """
    linprog = _linprog()
    optimum = solve_objective(stoichiometry, objective, lower, upper)
    floor = fraction_of_optimum * optimum
    a_eq = [list(row) for row in stoichiometry]
    b_eq = [0.0] * len(stoichiometry)
    # Hold the objective at (a fraction of) its optimum: objective . v >= floor, written for a
    # <=-form solver as -objective . v <= -floor.
    a_ub = [[-x for x in objective]]
    b_ub = [-floor]
    bounds = list(zip(lower, upper))
    ranges: list[tuple[float, float]] = []
    for i in range(len(objective)):
        select = [1.0 if j == i else 0.0 for j in range(len(objective))]
        lo = linprog(c=select, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
        hi = linprog(
            c=[-x for x in select], A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs"
        )
        if not lo.success or not hi.success:
            raise InfeasibleFba(f"flux-variability problem is not solvable for reaction {i}")
        ranges.append((float(lo.fun), float(-hi.fun)))
    return ranges


def _internal_reactions(stoichiometry: Sequence[Sequence[float]]) -> list[int]:
    """Reaction (column) indices that touch more than one metabolite — the internal reactions.

    A reaction with a single nonzero stoichiometric entry crosses the system boundary (an exchange,
    demand, or sink); only reactions internal to the network can close a stoichiometric cycle, so
    those are the ones the thermodynamic loop law constrains. This is the same structural boundary
    test community tools use, and it needs no metadata beyond S itself.
    """
    n_reactions = len(stoichiometry[0]) if stoichiometry else 0
    internal = []
    for j in range(n_reactions):
        touched = sum(1 for row in stoichiometry if row[j] != 0.0)
        if touched > 1:
            internal.append(j)
    return internal


def loopless_flux_variability(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    fraction_of_optimum: float = 1.0,
    reactions: Sequence[int] | None = None,
) -> list[tuple[float, float]]:
    """Flux variability with thermodynamically infeasible internal loops removed.

    Plain :func:`flux_variability` can report a spuriously wide interval for a reaction that sits on
    an internal stoichiometric cycle: the cycle satisfies the mass balance S·v = 0 yet carries no
    net thermodynamic driving force, so its flux is a solver artifact, not real flexibility. This
    adds the loop law (Schellenberger et al. 2011): every internal reaction's flux must be
    sign-opposed to a *conservative* energy field — one orthogonal to every internal cycle, so no
    cycle runs uphill — encoded as a mixed-integer constraint. The reported range is then the one a
    physically realizable flux distribution can actually reach.

    ``reactions`` optionally restricts the computation to a subset of reaction indices; the result
    is then one ``(min, max)`` per requested index, in the order given. This matters because each
    reaction costs a mixed-integer solve — on a genome-scale model, checking only the few reactions
    you care about is the difference between seconds and hours. When ``None`` (the default) every
    reaction is computed, in reaction order.

    On a model with no internal loops the null space of the internal stoichiometry is trivial and
    the result equals :func:`flux_variability`. The big-M encoding assumes sanely-bounded fluxes (as
    a curated core model has); a model shipping ±1e6 placeholder bounds should have them tightened
    first, or the mixed-integer solve is ill-conditioned. Needs the ``fba`` extra (scipy).
    """
    import numpy as np
    from scipy.linalg import null_space
    from scipy.optimize import Bounds, LinearConstraint

    milp = _milp()
    n = len(objective)
    targets = list(range(n)) if reactions is None else list(reactions)
    internal = _internal_reactions(stoichiometry)
    m = len(internal)
    s_matrix = [list(row) for row in stoichiometry]
    s_internal = np.array([[row[j] for j in internal] for row in s_matrix], dtype=float)
    cycles = null_space(s_internal) if m else np.zeros((0, 0))
    if cycles.shape[1] == 0:
        # No internal cycle carries flux, so no loop can inflate a range: plain FVA is already loopless.
        full = flux_variability(
            stoichiometry, objective, lower, upper, fraction_of_optimum=fraction_of_optimum
        )
        return [full[i] for i in targets]

    optimum = solve_objective(stoichiometry, objective, lower, upper)
    floor = fraction_of_optimum * optimum
    # Big-M for the sign coupling must dominate every reaction's own flux bound, or it would clip a
    # legitimately large flux; the energy scale reuses the same M (only g's sign matters). This
    # assumes sanely-bounded fluxes: a model that ships ±1e6 placeholder bounds forces big_m ≈ 1e6
    # and the mixed-integer solve becomes ill-conditioned — tighten such bounds before calling.
    finite_bounds = [abs(b) for b in lower] + [abs(b) for b in upper if b is not None]
    big_m = max(1000.0, *finite_bounds) if finite_bounds else 1000.0
    epsilon = 1.0

    # Variables x = [ v (n fluxes) | a (m binaries, the sign of each internal flux) | g (m energies) ].
    nvar = n + 2 * m
    a0, g0 = n, n + m  # column offsets of the a- and g-blocks

    def _row() -> list[float]:
        return [0.0] * nvar

    rows: list[list[float]] = []
    lb: list[float] = []
    ub: list[float] = []

    # Steady state S·v = 0.
    for s_row in s_matrix:
        row = _row()
        row[:n] = s_row
        rows.append(row)
        lb.append(0.0)
        ub.append(0.0)
    # Hold the objective at (a fraction of) its optimum.
    obj_row = _row()
    obj_row[:n] = list(objective)
    rows.append(obj_row)
    lb.append(floor)
    ub.append(np.inf)
    # Per internal reaction: couple flux sign to the binary, and the energy to the binary.
    for k, r in enumerate(internal):
        # a=1 ⟹ vᵣ ∈ [0, M]; a=0 ⟹ vᵣ ∈ [−M, 0].  (expression vᵣ − M·a ∈ [−M, 0])
        sign_row = _row()
        sign_row[r], sign_row[a0 + k] = 1.0, -big_m
        rows.append(sign_row)
        lb.append(-big_m)
        ub.append(0.0)
        # a=1 ⟹ gₖ ≤ −ε (forward runs downhill); a=0 ⟹ gₖ ≥ +ε (reverse runs downhill).
        # Both fit one row: gₖ + M·a ∈ [ε, M − ε].
        energy_row = _row()
        energy_row[g0 + k], energy_row[a0 + k] = 1.0, big_m
        rows.append(energy_row)
        lb.append(epsilon)
        ub.append(big_m - epsilon)
    # The energy field is conservative: orthogonal to every internal cycle (Kᵀ·g = 0).
    for c in range(cycles.shape[1]):
        row = _row()
        for k in range(m):
            row[g0 + k] = float(cycles[k, c])
        rows.append(row)
        lb.append(0.0)
        ub.append(0.0)

    constraint = LinearConstraint(np.array(rows), np.array(lb), np.array(ub))
    var_lb = [*lower, *([0.0] * m), *([-big_m] * m)]
    var_ub = [b if b is not None else np.inf for b in upper] + [1.0] * m + [big_m] * m
    bounds = Bounds(np.array(var_lb, dtype=float), np.array(var_ub, dtype=float))
    integrality = np.array([0] * n + [1] * m + [0] * m)

    ranges: list[tuple[float, float]] = []
    for i in targets:
        select = _row()
        select[i] = 1.0
        lo = milp(c=select, constraints=constraint, integrality=integrality, bounds=bounds)
        hi = milp(
            c=[-x for x in select], constraints=constraint, integrality=integrality, bounds=bounds
        )
        if not lo.success or not hi.success:
            raise InfeasibleFba(f"loopless flux-variability is not solvable for reaction {i}")
        ranges.append((float(lo.fun), float(-hi.fun)))
    return ranges


@dataclass(frozen=True)
class ProductionEnvelope:
    """The growth-vs-byproduct trade-off: a target reaction's feasible flux at each growth level.

    Introduced by Varma & Palsson (1994), this is the phenotypic phase plane a metabolic-engineering
    paper reports when it claims a strain can secrete a product *and* grow: the frontier of maximum
    product flux achievable at each growth rate. Reproducing that curve is a distinct claim from a
    single objective value — it is the whole Pareto front, not one point on it.

    ``growth`` is the grid of objective (growth) levels from 0 to the unconstrained optimum;
    ``target_min`` and ``target_max`` are the least and greatest the target reaction's flux can take
    while the objective is held at that level (from an LP min/max, so alternate optima are handled
    honestly). ``target_max`` is the production frontier. All three are aligned tuples, one entry per
    grid point, in increasing-growth order.
    """

    growth: tuple[float, ...]
    target_min: tuple[float, ...]
    target_max: tuple[float, ...]


def production_envelope(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    target: int,
    points: int = 20,
) -> ProductionEnvelope:
    """The production envelope of a target reaction versus the objective (spec: constraint-based-class).

    Sweeps the objective (growth) from 0 to its unconstrained optimum over ``points`` levels; at each
    level the objective is pinned by an equality (``objective · v == level``) and the target
    reaction's flux is both minimized and maximized. The upper boundary (``target_max``) is the
    classic concave frontier: because the feasible set at each level is a convex polytope and the
    pinning constraint is linear in the level, the maximum target flux is a concave, piecewise-linear
    function of growth — a product's yield trades off against growth along straight segments with a
    breakpoint where a new pathway (e.g. overflow secretion) engages.

    ``target`` is the reaction's column index. ``points`` must be at least 2 (the endpoints).
    Raises :class:`InfeasibleFba` if a level is not solvable. Needs the ``fba`` extra (scipy).
    """
    if points < 2:
        raise ValueError("a production envelope needs at least 2 points (the two endpoints)")
    linprog = _linprog()
    n = len(objective)
    max_growth = solve_objective(stoichiometry, objective, lower, upper)
    # Pin the objective at each swept level with an equality row appended to the steady state.
    a_eq = [list(row) for row in stoichiometry] + [list(objective)]
    bounds = list(zip(lower, upper))
    select = [1.0 if j == target else 0.0 for j in range(n)]
    growth: list[float] = []
    target_min: list[float] = []
    target_max: list[float] = []
    for k in range(points):
        level = max_growth * k / (points - 1)
        b_eq = [0.0] * len(stoichiometry) + [level]
        lo = linprog(c=select, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
        hi = linprog(c=[-x for x in select], A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
        if not lo.success or not hi.success:
            raise InfeasibleFba(f"the production envelope is not solvable at growth level {level:.6g}")
        growth.append(level)
        target_min.append(float(lo.fun))
        target_max.append(float(-hi.fun))
    return ProductionEnvelope(
        growth=tuple(growth), target_min=tuple(target_min), target_max=tuple(target_max)
    )


@dataclass(frozen=True)
class ParsimoniousSolution:
    """A parsimonious (pFBA) flux distribution: the minimal-total-flux vector that stays optimal.

    ``fluxes`` is one flux per reaction (in reaction order); ``total_flux`` is the minimized
    Σ|vᵢ|; ``objective_value`` is the optimum the solution preserves. Where plain FBA leaves many
    reactions free among alternate optima — so :func:`judge_flux` must abstain — pFBA selects the
    single distribution that achieves the optimum with the least total enzymatic flux, the standard
    parsimony assumption (Lewis et al. 2010). That assumption is load-bearing: a flux certified this
    way is reproduced *under parsimony*, and should be qualified accordingly.
    """

    fluxes: tuple[float, ...]
    total_flux: float
    objective_value: float


def parsimonious_fluxes(
    stoichiometry: Sequence[Sequence[float]],
    objective: Sequence[float],
    lower: Sequence[float],
    upper: Sequence[float | None],
    *,
    fraction_of_optimum: float = 1.0,
) -> ParsimoniousSolution:
    """The parsimonious FBA solution: minimize total flux Σ|vᵢ| while holding the objective optimal.

    A two-stage LP (Lewis et al. 2010): first find the optimum, then, among all flux vectors that
    still reach (a ``fraction_of_optimum`` of) it, choose the one minimizing total flux. Total flux
    is linearized with per-reaction auxiliaries aᵢ ≥ |vᵢ|, so the whole thing stays a single LP.
    Unlike a raw optimal vector, this one is canonical — the biologically-motivated tie-break among
    alternate optima. Raises :class:`InfeasibleFba` if unsolvable. Needs the ``fba`` extra (scipy).
    """
    linprog = _linprog()
    n = len(objective)
    optimum = solve_objective(stoichiometry, objective, lower, upper)
    floor = fraction_of_optimum * optimum
    # Variables: the n fluxes v, then n auxiliaries a. Minimize Σ a (the aᵢ pin down |vᵢ|).
    cost = [0.0] * n + [1.0] * n
    # Steady state on v only; hold the objective at its optimum (−objective·v ≤ −floor).
    a_eq = [[*row, *([0.0] * n)] for row in stoichiometry]
    b_eq = [0.0] * len(stoichiometry)
    a_ub = [[-x for x in objective] + [0.0] * n]
    b_ub = [-floor]
    # aᵢ ≥ vᵢ and aᵢ ≥ −vᵢ, i.e. vᵢ − aᵢ ≤ 0 and −vᵢ − aᵢ ≤ 0.
    for i in range(n):
        upper_row = [0.0] * (2 * n)
        upper_row[i], upper_row[n + i] = 1.0, -1.0
        a_ub.append(upper_row)
        b_ub.append(0.0)
        lower_row = [0.0] * (2 * n)
        lower_row[i], lower_row[n + i] = -1.0, -1.0
        a_ub.append(lower_row)
        b_ub.append(0.0)
    bounds = list(zip(lower, upper)) + [(0.0, None)] * n
    result = linprog(c=cost, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not result.success:
        raise InfeasibleFba(f"the parsimonious-flux problem is not solvable: {result.message}")
    fluxes = tuple(float(v) for v in result.x[:n])
    total_flux = float(sum(result.x[n:]))
    return ParsimoniousSolution(fluxes=fluxes, total_flux=total_flux, objective_value=optimum)


def judge_flux(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    reported: float,
    interval: tuple[float, float],
    pin_tolerance: float = 1e-6,
    tolerance: Tolerance | None = None,
    reference_kind: ReferenceKind = ReferenceKind.NUMERIC,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Judge a reported reaction flux against its flux-variability interval — honestly.

    ``interval`` is the ``(min, max)`` this reaction can take at the optimum (from
    :func:`flux_variability`). The verdict follows the spec's honesty rule for alternate optima
    (spec: constraint-based-class), which is design goal 2 in this setting:

    * The interval **pins** the flux (min == max within ``pin_tolerance``) and contains the
      reported value → the model uniquely produces it: judged as reproduced via the scalar oracle.
    * The reported value lies **inside a non-trivial interval** → the model is *consistent with*
      the value but does not determine it; certifying "reproduced" would overstate, so we abstain
      (``not-evaluable``) rather than claim a pass the alternate optima do not earn.
    * The reported value lies **outside** the feasible interval → the model cannot achieve this
      flux at the optimum: judged against the nearest feasible flux, so it lands partial/failed
      (and, like any non-pass, requires an ``attribution``).
    """
    lo, hi = interval
    slack = pin_tolerance * max(1.0, abs(lo), abs(hi))
    inside = lo - slack <= reported <= hi + slack
    pinned = (hi - lo) <= slack

    if inside and pinned:
        return judge_scalar(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reported=reported,
            predicted=(lo + hi) / 2.0,
            reference_kind=reference_kind,
            tolerance=tolerance,
            attribution=attribution,
            assumption_qualified=assumption_qualified,
        )
    if inside:
        return not_evaluable(
            claim_id=claim_id,
            quantity=quantity,
            source_location=source_location,
            reason=(
                f"the model does not uniquely determine this flux at the optimum: the "
                f"flux-variability interval [{lo:.4g}, {hi:.4g}] contains the reported "
                f"{reported:.4g} but leaves it free (alternate optima)"
            ),
            reference_kind=reference_kind,
        )
    nearest = lo if reported < lo else hi
    return judge_scalar(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        reported=reported,
        predicted=nearest,
        reference_kind=reference_kind,
        tolerance=tolerance,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


@dataclass(frozen=True)
class FrogFingerprint:
    """A standardized, solver-independent reproducibility fingerprint for a constraint-based model.

    Named for the FROG analysis the field uses (Flux optimum, Reaction variability, Objective,
    Gene/reaction deletion). It bundles the results the constraint-based-class spec names — the
    optimal objective value, each reaction's flux-variability interval, the objective remaining
    after each reaction is deleted, and the objective remaining after each gene is deleted — so a
    verdict can be the comparison of two fingerprints rather than of a single number. Gene deletion
    is populated when the model carries gene–reaction associations
    (:func:`reprolith.ingest_fbc_sbml`); a model without them simply has an empty gene section.
    """

    reaction_ids: tuple[str, ...]
    objective_value: float
    variability: tuple[tuple[float, float], ...]
    deletion_objectives: tuple[float, ...]
    gene_ids: tuple[str, ...] = ()
    gene_deletion_objectives: tuple[float, ...] = ()


@dataclass(frozen=True)
class FrogComparison:
    """The component-wise agreement of two FROG fingerprints, with the disagreements named."""

    objective_agrees: bool
    variability_agrees: bool
    deletion_agrees: bool
    disagreements: tuple[str, ...]
    gene_deletion_agrees: bool = True

    @property
    def agrees(self) -> bool:
        return (
            self.objective_agrees
            and self.variability_agrees
            and self.deletion_agrees
            and self.gene_deletion_agrees
        )


def frog_fingerprint(model: FbaModel, *, fraction_of_optimum: float = 1.0) -> FrogFingerprint:
    """Compute the FROG fingerprint of a constraint-based model (spec: constraint-based-class).

    The objective value and each reaction's variability interval come from :func:`solve_objective`
    and :func:`flux_variability`; the deletion objective for a reaction is the optimum with that
    reaction's flux constrained to zero (0.0 if the knockout makes the model infeasible). Every
    component is well-defined regardless of alternate optima, so the fingerprint is portable.
    """
    objective_value = solve_objective(
        model.stoichiometry, model.objective, model.lower, model.upper
    )
    variability = flux_variability(
        model.stoichiometry,
        model.objective,
        model.lower,
        model.upper,
        fraction_of_optimum=fraction_of_optimum,
    )
    deletion: list[float] = []
    for i in range(len(model.reaction_ids)):
        knocked_lower = [0.0 if j == i else lo for j, lo in enumerate(model.lower)]
        knocked_upper: list[float | None] = [
            0.0 if j == i else up for j, up in enumerate(model.upper)
        ]
        try:
            deletion.append(
                solve_objective(model.stoichiometry, model.objective, knocked_lower, knocked_upper)
            )
        except InfeasibleFba:
            deletion.append(0.0)
    gene_ids = model.genes()
    gene_deletion = tuple(_objective_without_gene(model, gene) for gene in gene_ids)
    return FrogFingerprint(
        reaction_ids=model.reaction_ids,
        objective_value=objective_value,
        variability=tuple(variability),
        deletion_objectives=tuple(deletion),
        gene_ids=gene_ids,
        gene_deletion_objectives=gene_deletion,
    )


def _close(a: float, b: float, rel_tol: float) -> bool:
    return abs(a - b) <= rel_tol * max(1.0, abs(a), abs(b))


def compare_frog(
    computed: FrogFingerprint, reported: FrogFingerprint, *, rel_tol: float = 1e-6
) -> FrogComparison:
    """Compare two FROG fingerprints component-wise, aligning reactions by id.

    The objective values, each shared reaction's variability bounds, and each shared reaction's
    deletion objective must agree within ``rel_tol``. Reactions present in only one fingerprint are
    recorded as disagreements, so a structural mismatch is never hidden by a numeric pass.
    """
    disagreements: list[str] = []

    objective_agrees = _close(computed.objective_value, reported.objective_value, rel_tol)
    if not objective_agrees:
        disagreements.append(
            f"objective {computed.objective_value:.6g} != {reported.objective_value:.6g}"
        )

    reported_index = {rid: i for i, rid in enumerate(reported.reaction_ids)}
    only_computed = [r for r in computed.reaction_ids if r not in reported_index]
    only_reported = [r for r in reported.reaction_ids if r not in set(computed.reaction_ids)]
    for rid in only_computed + only_reported:
        disagreements.append(f"reaction {rid} present in only one fingerprint")

    variability_agrees = True
    deletion_agrees = True
    for i, rid in enumerate(computed.reaction_ids):
        if rid not in reported_index:
            variability_agrees = deletion_agrees = False
            continue
        j = reported_index[rid]
        (clo, chi), (rlo, rhi) = computed.variability[i], reported.variability[j]
        if not (_close(clo, rlo, rel_tol) and _close(chi, rhi, rel_tol)):
            variability_agrees = False
            disagreements.append(
                f"variability {rid}: [{clo:.6g}, {chi:.6g}] != [{rlo:.6g}, {rhi:.6g}]"
            )
        if not _close(computed.deletion_objectives[i], reported.deletion_objectives[j], rel_tol):
            deletion_agrees = False
            disagreements.append(
                f"deletion {rid}: {computed.deletion_objectives[i]:.6g} != "
                f"{reported.deletion_objectives[j]:.6g}"
            )

    if only_computed or only_reported:
        variability_agrees = deletion_agrees = False

    gene_deletion_agrees = True
    reported_gene = {gid: j for j, gid in enumerate(reported.gene_ids)}
    only_computed_genes = [g for g in computed.gene_ids if g not in reported_gene]
    only_reported_genes = [g for g in reported.gene_ids if g not in set(computed.gene_ids)]
    for gid in only_computed_genes + only_reported_genes:
        disagreements.append(f"gene {gid} present in only one fingerprint")
        gene_deletion_agrees = False
    for i, gid in enumerate(computed.gene_ids):
        if gid not in reported_gene:
            continue
        j = reported_gene[gid]
        if not _close(
            computed.gene_deletion_objectives[i], reported.gene_deletion_objectives[j], rel_tol
        ):
            gene_deletion_agrees = False
            disagreements.append(
                f"gene-deletion {gid}: {computed.gene_deletion_objectives[i]:.6g} != "
                f"{reported.gene_deletion_objectives[j]:.6g}"
            )

    return FrogComparison(
        objective_agrees=objective_agrees,
        variability_agrees=variability_agrees,
        deletion_agrees=deletion_agrees,
        disagreements=tuple(disagreements),
        gene_deletion_agrees=gene_deletion_agrees,
    )


def judge_fingerprint(
    *,
    claim_id: str,
    quantity: str,
    source_location: str,
    comparison: FrogComparison,
    attribution: Attribution | None = None,
    assumption_qualified: bool = False,
) -> ClaimAssessment:
    """Turn a FROG fingerprint comparison into a certificate-ready assessment.

    When a paper or its curation ships a fingerprint, the verdict is the comparison of
    fingerprints, not of a single number (spec: constraint-based-class). This maps that comparison
    onto the shared assessment contract: the fingerprints agreeing reproduces; otherwise it fails,
    with the named component disagreements recorded as the discrepancy so the verdict stays
    auditable. Like any non-pass, a failure requires an ``attribution``.
    """
    discrepancy = (
        "fingerprints agree"
        if comparison.agrees
        else "; ".join(comparison.disagreements)
    )
    return assess_match(
        claim_id=claim_id,
        quantity=quantity,
        source_location=source_location,
        matched=comparison.agrees,
        method=ComparisonMethod.FINGERPRINT_COMPARISON,
        discrepancy=discrepancy,
        attribution=attribution,
        assumption_qualified=assumption_qualified,
    )


_Element = TypeVar("_Element")


def essentiality_agreement(
    computed: frozenset[_Element], reported: frozenset[_Element]
) -> float:
    """Jaccard agreement of a computed and a reported essential set, over their union.

    Serves either essential set the class produces: the reaction indices from
    :func:`reaction_essentiality` or the gene labels from :func:`gene_essentiality` — the elements
    need only be hashable. 1.0 is a perfect match; 0.0 is complete disagreement; an empty union
    (nothing essential either way) counts as full agreement.
    """
    union = computed | reported
    if not union:
        return 1.0
    return len(computed & reported) / len(union)


__all__ = [
    "FbaModel",
    "FbaUnavailable",
    "FrogComparison",
    "FrogFingerprint",
    "InfeasibleFba",
    "ParsimoniousSolution",
    "ProductionEnvelope",
    "ShadowPrices",
    "compare_frog",
    "essentiality_agreement",
    "flux_variability",
    "frog_fingerprint",
    "gene_essentiality",
    "judge_fingerprint",
    "judge_flux",
    "judge_objective",
    "parsimonious_fluxes",
    "production_envelope",
    "reaction_essentiality",
    "shadow_prices",
    "solve_objective",
    "synthetic_lethal_reactions",
]
