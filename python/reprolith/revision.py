"""Tracked revision of a dossier (bootstrap task 2.4).

A dossier is reviewable and correctable without re-deriving it from scratch: when a reviewer
identifies a mis-extracted equation, parameter, or claim, the correction is applied as a
tracked revision with the corrector and rationale recorded, and the original extraction
remains retrievable (spec: ``paper-ingestion`` — "Ingestion is inspectable and revisable").

Dossiers are immutable, so a correction produces a new dossier plus a :class:`DossierRevision`
that links back to the one it corrects by content digest. :class:`DossierHistory` keeps every
revision retrievable and can walk the chain back to the original.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import content_hash
from .dossier import Dossier


def dossier_digest(dossier: Dossier) -> str:
    """The stable content digest of a dossier — its identity across revisions."""
    return content_hash(dossier.to_dict())


@dataclass(frozen=True)
class DossierRevision:
    """A corrected dossier plus who corrected it, why, and which dossier it supersedes."""

    dossier: Dossier
    corrector: str
    rationale: str
    at: str
    supersedes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "dossier": self.dossier.to_dict(),
            "corrector": self.corrector,
            "rationale": self.rationale,
            "at": self.at,
            "supersedes": self.supersedes,
        }


def revise(
    prior: Dossier,
    corrected: Dossier,
    *,
    corrector: str,
    rationale: str,
    at: str,
) -> DossierRevision:
    """Apply ``corrected`` as a tracked revision of ``prior``.

    The prior dossier is not mutated; the revision links to it by digest, so the original
    extraction remains retrievable alongside the correction. A rationale is required — a
    correction with no stated reason is not a tracked revision.
    """
    if not rationale.strip():
        raise ValueError("a tracked revision must record the corrector's rationale")
    if dossier_digest(corrected) == dossier_digest(prior):
        # A no-op "correction" would supersede itself by digest, giving the lineage a self-loop.
        raise ValueError("a tracked revision must change the dossier it corrects")
    return DossierRevision(
        dossier=corrected,
        corrector=corrector,
        rationale=rationale,
        at=at,
        supersedes=dossier_digest(prior),
    )


class DossierHistory:
    """A retrievable store of dossiers and the revisions between them.

    Recording a correction never displaces the dossier it corrects: both stay retrievable by
    digest, and :meth:`chain` reconstructs the revision lineage newest-first.
    """

    def __init__(self) -> None:
        self._dossiers: dict[str, Dossier] = {}
        self._prior_of: dict[str, str] = {}

    def record_original(self, dossier: Dossier) -> str:
        """Store the first extraction and return its digest."""
        digest = dossier_digest(dossier)
        self._dossiers[digest] = dossier
        return digest

    def record_revision(self, revision: DossierRevision) -> str:
        """Store a revision (and its link to the dossier it corrects); return its digest."""
        digest = dossier_digest(revision.dossier)
        self._dossiers[digest] = revision.dossier
        self._prior_of[digest] = revision.supersedes
        return digest

    def get(self, digest: str) -> Dossier | None:
        """Retrieve a dossier by its content digest, original or revised."""
        return self._dossiers.get(digest)

    def chain(self, dossier: Dossier) -> tuple[Dossier, ...]:
        """The revision lineage of ``dossier``, newest first, back to the original."""
        lineage: list[Dossier] = [dossier]
        current = dossier_digest(dossier)
        seen = {current}
        while current in self._prior_of:
            prior_digest = self._prior_of[current]
            if prior_digest in seen:
                break  # a self- or cyclic supersession can't extend the lineage; never loop on it
            prior = self._dossiers.get(prior_digest)
            if prior is None:
                break
            lineage.append(prior)
            seen.add(prior_digest)
            current = prior_digest
        return tuple(lineage)


__all__ = ["DossierHistory", "DossierRevision", "dossier_digest", "revise"]
