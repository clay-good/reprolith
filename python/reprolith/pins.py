"""The revision a pure-Python solver pins (spec: verification-queue — freshness and re-opening).

A certificate is re-opened for review when its engine pin differs from the current one
(:func:`reprolith.certificates_needing_review`). For the classes whose solver *is* this package —
the Gillespie SSA, the finite-difference reaction-diffusion solver, the attractor enumerator, and
the constraint-based analysis layer on top of the LP backend — the only moving part of the pin used
to be a package version that has never been bumped. Fixing a solver therefore left every
certificate that fix invalidates looking fresh: the freshness check compared two identical pins.

:func:`algorithm_revision` gives those pins something that actually moves: a digest over the source
of the modules that computed the result. It is deliberately blunt — it hashes the file bytes, so a
comment or docstring edit moves the revision too, and every affected certificate is flagged for
re-verification when nothing numeric changed. That is the safe direction of error (a needless
re-run costs seconds for a dependency-free solver; a missed one publishes a number the current code
would not produce), and it needs no human to remember to bump a constant, which is the failure this
exists to remove.

The judge is part of the computation, not a bystander: a class-default tolerance in
:mod:`reprolith.oracle`, and the rule in :mod:`reprolith.certificate` that turns per-claim
assessments into the headline verdict, decide what the solver's numbers *mean*. So a revision spans
the whole path from the solver to the verdict — the class's solver, any analysis layer between it
and the judge, the oracle, and the certificate rule — not the solver alone. A revision that stopped
at the solver would leave a fix to the layer above it invisible, which is the failure this exists
to remove.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

_HERE = Path(__file__).resolve().parent


@cache
def algorithm_revision(*modules: str) -> str:
    """A short digest of the named sibling modules' source, in the order given.

    ``modules`` are module names within this package (e.g. ``"stochastic"``, ``"oracle"``). The
    digest is over the files' bytes, so it is identical on every interpreter and platform that
    checks out the same source — a certificate's pin means the same thing wherever it is read.

    Raises :class:`RuntimeError` if a named module's source cannot be read. A pin that cannot
    state the revision of the code behind it must fail loudly rather than fall back to a value
    that reads as fresh.
    """
    if not modules:
        # sha256 of nothing is a perfectly well-formed digest, and a pin carrying it would read as
        # the revision of some code rather than of none at all.
        raise ValueError("a revision must name at least one module to take the revision of")
    digest = hashlib.sha256()
    for name in modules:
        path = _HERE / f"{name}.py"
        try:
            digest.update(path.read_bytes())
        except OSError as exc:  # pragma: no cover - only when the install has no source
            raise RuntimeError(
                f"cannot read the source of reprolith.{name} to pin its revision ({path}); "
                "a certificate cannot name the code that produced it"
            ) from exc
    return digest.hexdigest()[:12]


__all__ = ["algorithm_revision"]
