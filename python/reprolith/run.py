"""Running the pathway over the test set and scoring agreement (bootstrap tasks 7.1, 8.1).

This drives the blind self-validation run: every catalog entry yields a certificate, and the
result is scored against the ground-truth labels. An entry for which claims have been extracted
and verified is certified with them; an entry for which they have not is honestly ``blocked`` —
Reprolith abstains rather than manufacture a verdict it cannot support (design goal 2: a
confidently wrong verdict is worse than an honest blocked).

A ``blocked`` certificate here is not a failure to reproduce; it records the precise missing
input — the paper's machine-checkable claims — so the gap is evidence for the field, not a
silent gap. Scoring is a pure function of certificates and labels, so the run is reproducible.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .agreement import AgreementReport, build_agreement_report
from .catalog import CatalogEntry
from .certificate import build_certificate
from .certify import Claim, certify_model
from .enums import LifecycleState, OverallVerdict
from .model import Assumption, Certificate, EnginePin, PaperIdentity

NO_CLAIMS_REASON = (
    "no machine-checkable claims extracted from the shipped model artifact; "
    "reproduction requires the paper's targetable claims (manuscript claim extraction)"
)


def _paper_of(entry: CatalogEntry) -> PaperIdentity:
    ids = entry.identifiers
    return PaperIdentity(title=ids.title, doi=ids.doi, pubmed_id=ids.pubmed_id)


def blocked_certificate(
    paper: PaperIdentity,
    engine_pin: EnginePin,
    *,
    reason: str = NO_CLAIMS_REASON,
) -> Certificate:
    """A certificate that abstains: no evaluable claims, with the missing input recorded."""
    return build_certificate(
        paper=paper,
        engine_pin=engine_pin,
        assessments=(),
        gap_report=(reason,),
    )


def certified_from_claims(
    claims_dataset: dict[str, Any],
    *,
    base_dir: Path | str,
    engine_pin: EnginePin,
) -> dict[str, Certificate]:
    """Certify every entry in a claims dataset, keyed by accession.

    Each dataset entry names a model file (resolved under ``base_dir``), the paper, and the
    verified claims; this runs :func:`certify_model` for each and returns the certificates.
    Needs the optional engine extra. Entries with no claims dataset stay blocked in the run.
    """
    base = Path(base_dir)
    certificates: dict[str, Certificate] = {}
    for accession, entry in claims_dataset["entries"].items():
        sbml = (base / entry["model_file"]).read_text(encoding="utf-8")
        claims = [Claim.from_record(record) for record in entry["claims"]]
        assumptions = [Assumption(**record) for record in entry.get("assumptions", [])]
        certificates[accession] = certify_model(
            sbml,
            paper=PaperIdentity(**entry["paper"]),
            engine_pin=engine_pin,
            claims=claims,
            assumptions=assumptions,
            duration=float(entry["duration"]),
            steps=int(entry.get("steps", 480)),
        )
    return certificates


def load_claims_dataset(path: Path | str) -> dict[str, Any]:
    """Load a claims dataset (the verified extracted claims per entry)."""
    with open(path, encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


# The lifecycle path each outcome walks, so a certified/blocked entry's history is the honest
# record of the pathway (ingest -> reconstruct -> verify -> outcome), not a single jump.
_TO_CERTIFIED = (
    LifecycleState.INGESTING,
    LifecycleState.INGESTED,
    LifecycleState.RECONSTRUCTING,
    LifecycleState.RECONSTRUCTED,
    LifecycleState.VERIFYING,
    LifecycleState.CERTIFIED,
)
_TO_FAILED = _TO_CERTIFIED[:-1] + (LifecycleState.FAILED,)
_TO_BLOCKED = (LifecycleState.INGESTING, LifecycleState.BLOCKED)


def advance_to_outcome(
    entry: CatalogEntry,
    overall: OverallVerdict,
    *,
    at: str,
    actor: str,
    blocked_reason: str = NO_CLAIMS_REASON,
) -> None:
    """Walk a queued entry to the lifecycle state matching its run outcome, recording each move.

    ``reproduced``/``partially-reproduced`` end at ``certified``; ``not-reproduced`` at
    ``failed``; ``blocked`` at ``blocked`` with the missing input. Only advances an entry still
    in ``queued`` (a re-run does not double-record).
    """
    if entry.state is not LifecycleState.QUEUED:
        return
    path: tuple[LifecycleState, ...]
    if overall is OverallVerdict.BLOCKED:
        path = _TO_BLOCKED
    elif overall is OverallVerdict.NOT_REPRODUCED:
        path = _TO_FAILED
    else:
        path = _TO_CERTIFIED
    for state in path:
        missing = (blocked_reason,) if state is LifecycleState.BLOCKED else ()
        entry.transition(state, at=at, actor=actor, reason="blind run", missing_inputs=missing)


def run_test_set(
    entries: Sequence[CatalogEntry],
    *,
    engine_pin: EnginePin,
    certified: Mapping[str, Certificate] | None = None,
    blocked_reason: str = NO_CLAIMS_REASON,
    advance: bool = False,
    at: str = "blind-run",
    actor: str = "reprolith",
) -> tuple[list[Certificate], AgreementReport]:
    """Produce a certificate for every entry and score agreement with ground truth.

    ``certified`` maps an entry's BioModels accession (or title) to a certificate already
    produced for it; any entry not present is blocked. With ``advance``, each entry's lifecycle
    is walked to its outcome state so the catalog records the run. Returns the certificates in
    entry order and the agreement report comparing each entry's overall verdict to its label.
    """
    certified = certified or {}
    certificates: list[Certificate] = []
    scored: list[tuple[CatalogEntry, OverallVerdict]] = []
    for entry in entries:
        key = entry.identifiers.accession or entry.identifiers.title
        certificate = certified.get(key) or blocked_certificate(
            _paper_of(entry), engine_pin, reason=blocked_reason
        )
        certificates.append(certificate)
        scored.append((entry, certificate.overall))
        if advance:
            advance_to_outcome(entry, certificate.overall, at=at, actor=actor,
                               blocked_reason=blocked_reason)
    return certificates, build_agreement_report(scored)


__all__ = [
    "NO_CLAIMS_REASON",
    "advance_to_outcome",
    "blocked_certificate",
    "certified_from_claims",
    "load_claims_dataset",
    "run_test_set",
]
