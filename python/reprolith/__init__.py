"""Reprolith — auto-reproduction & certification engine for the biomedical modeling literature.

This is the engine skeleton: the domain shapes a certificate is built from, the rule
that derives its verdict, the inescapable scope statement, and the determinism harness
that makes a certificate byte-reproducible. The ingestion, reconstruction, and
simulation-oracle stages described in ``openspec/`` build on top of these shapes.
"""

from __future__ import annotations

from .agreement import AgreementReport, EntryAgreement, build_agreement_report
from .canonical import canonical_bytes, canonical_json, content_hash
from .catalog import (
    BlindEntry,
    Catalog,
    CatalogEntry,
    GroundTruth,
    Identifiers,
    IllegalTransition,
    Transition,
)
from .certificate import build_certificate, derive_overall
from .determinism import certificate_digest, same_modulo_run_metadata
from .enums import (
    LifecycleState,
    ModelClass,
    OverallVerdict,
    ReproductionLevel,
    Verdict,
)
from .model import (
    Assumption,
    Certificate,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    RunMetadata,
)
from .oracle import (
    Attribution,
    ComparisonMethod,
    FailureMode,
    Fault,
    ReferenceKind,
    Tolerance,
    ToleranceSource,
    default_tolerance,
    judge_curve,
    judge_scalar,
    normalized_curve_distance,
    not_evaluable,
    relative_error,
)
from .query import ReprolithQuery
from .render import claim_counts, gap_items, render_human, render_machine
from .scope import Scope
from .supersession import CertificateLedger, describe_changes

__version__ = "0.0.1"

__all__ = [
    "AgreementReport",
    "Assumption",
    "Attribution",
    "BlindEntry",
    "EntryAgreement",
    "Catalog",
    "CatalogEntry",
    "CertificateLedger",
    "Certificate",
    "ClaimAssessment",
    "ComparisonMethod",
    "EnginePin",
    "Fault",
    "FailureMode",
    "GroundTruth",
    "Identifiers",
    "IllegalTransition",
    "LifecycleState",
    "ModelClass",
    "OverallVerdict",
    "PaperIdentity",
    "ReferenceKind",
    "ReproductionLevel",
    "ReprolithQuery",
    "RunMetadata",
    "Scope",
    "Tolerance",
    "ToleranceSource",
    "Transition",
    "Verdict",
    "build_agreement_report",
    "build_certificate",
    "canonical_bytes",
    "canonical_json",
    "certificate_digest",
    "claim_counts",
    "content_hash",
    "default_tolerance",
    "derive_overall",
    "describe_changes",
    "gap_items",
    "judge_curve",
    "judge_scalar",
    "normalized_curve_distance",
    "not_evaluable",
    "relative_error",
    "render_human",
    "render_machine",
    "same_modulo_run_metadata",
    "__version__",
]
