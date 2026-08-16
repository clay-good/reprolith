"""Seeding's intake gates: quality and licensing/ethics (spec: catalog-seeding).

Before a candidate paper becomes catalog work, seeding screens it (spec: catalog-seeding — "Quality
gate before a candidate becomes work" and "Licensing and ethical gating"). Two questions decide
what happens:

* **Quality** — does it plausibly contain a reproducible computational model *and* a targetable
  claim? A candidate that clearly contains no model is **set aside** with a reason; an *uncertain*
  one is **retained** as backlog rather than dropped, because premature discarding loses the
  un-curated tail where the "what was missing" reports matter most.
* **Licensing and ethics** — what may lawfully be stored, and is the required input obtainable? Only
  what the source's terms permit is storable (metadata always; full text and the model only when the
  licence allows); a candidate whose model cannot be lawfully obtained is admitted but flagged
  **blocked on access**, not failed; and anything that could carry patient-level or personal data is
  excluded outright — Reprolith seeds published models, not primary human data.

This is a pure policy layer: dependency-free, deterministic, and observable, so no candidate's fate
is a black box.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Licence identifiers that permit redistributing the full text and the model artifact, not only
# metadata. Anything else (restricted, unknown) is treated as metadata-only, conservatively.
_OPEN_LICENCES = frozenset({"cc0", "cc-by", "cc-by-sa", "public-domain"})


class Screening(str, Enum):
    """What seeding does with a candidate at intake."""

    ACCEPT = "accept"  # plausibly a reproducible model + claim; admit it as work
    RETAIN = "retain"  # uncertain; keep as backlog rather than drop
    SET_ASIDE = "set-aside"  # clearly not a target (no model) or ethically excluded


@dataclass(frozen=True)
class Candidate:
    """A seeding candidate before it becomes a catalog entry, with the signals a source provides.

    ``None`` on a quality signal means *unknown* — the honest default for un-curated intake, and the
    reason such a candidate is retained rather than accepted or dropped.
    """

    title: str
    source: str
    contains_model: bool | None = None
    has_targetable_claim: bool | None = None
    licence: str | None = None
    model_obtainable: bool = True
    carries_personal_data: bool = False


@dataclass(frozen=True)
class ScreeningResult:
    """The screening decision, with the reason and the licence-permitted storable content."""

    outcome: Screening
    reason: str
    storable: tuple[str, ...]
    blocked_on_access: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "storable": list(self.storable),
            "blocked_on_access": self.blocked_on_access,
        }


def storable_content(licence: str | None) -> tuple[str, ...]:
    """What a source's licence permits Reprolith to store and redistribute.

    Metadata and the citation are always storable (facts about the paper). The full text and the
    model artifact are storable only under an open licence; under a restricted or unknown licence
    only metadata is kept, so Reprolith never redistributes content it has no right to.
    """
    if licence and licence.lower() in _OPEN_LICENCES:
        return ("metadata", "citation", "full-text", "model")
    return ("metadata", "citation")


def screen_candidate(candidate: Candidate) -> ScreeningResult:
    """Screen a candidate at intake through the quality and licensing/ethics gates.

    Ethics gate first, then quality, then licensing. The result names the outcome, the reason, the
    licence-permitted storable content, and whether the candidate is blocked on access — everything
    a reviewer needs to see why the candidate holds its fate.
    """
    storable = storable_content(candidate.licence)

    # Ethics: never seed sources that could carry patient-level or personal data.
    if candidate.carries_personal_data:
        return ScreeningResult(
            outcome=Screening.SET_ASIDE,
            reason="excluded: source may carry patient-level or personal data",
            storable=(),
            blocked_on_access=False,
        )

    # Quality: a clear non-target is set aside; an uncertain candidate is retained as backlog.
    if candidate.contains_model is False:
        return ScreeningResult(
            outcome=Screening.SET_ASIDE,
            reason="no reproducible computational model apparent",
            storable=storable,
            blocked_on_access=False,
        )
    if candidate.contains_model is None or candidate.has_targetable_claim is None:
        return ScreeningResult(
            outcome=Screening.RETAIN,
            reason="uncertain whether it contains a model and a targetable claim; retained as backlog",
            storable=storable,
            blocked_on_access=not candidate.model_obtainable,
        )
    if not candidate.has_targetable_claim:
        return ScreeningResult(
            outcome=Screening.SET_ASIDE,
            reason="a model but no targetable claim to reproduce",
            storable=storable,
            blocked_on_access=False,
        )

    # Accepted as work — but if the model cannot be lawfully obtained it is admitted blocked on
    # access, not failed (there is a reproducible target, just not a fetchable input yet).
    blocked = not candidate.model_obtainable
    reason = (
        "reproducible model and targetable claim present, but the model cannot be lawfully obtained"
        if blocked
        else "reproducible model and targetable claim present"
    )
    return ScreeningResult(
        outcome=Screening.ACCEPT, reason=reason, storable=storable, blocked_on_access=blocked
    )


__all__ = ["Candidate", "Screening", "ScreeningResult", "screen_candidate", "storable_content"]
