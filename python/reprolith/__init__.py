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
from .certify import Claim, certify_model
from .determinism import certificate_digest, same_modulo_run_metadata
from .dossier import (
    Dossier,
    DossierClaim,
    Equation,
    ExtractionConfidence,
    Gap,
    GapKind,
    ModelArtifact,
    Parameter,
    estimate_difficulty,
)
from .engine import (
    EngineUnavailable,
    NonFiniteSimulation,
    engine_pin,
    engine_version,
    simulate,
)
from .enums import (
    LifecycleState,
    ModelClass,
    OverallVerdict,
    ReproductionLevel,
    Verdict,
)
from .fba import (
    FbaUnavailable,
    InfeasibleFba,
    essentiality_agreement,
    flux_variability,
    judge_flux,
    judge_objective,
    reaction_essentiality,
    solve_objective,
)
from .ingest import ingest_sbml
from .linter import LintResult, lint_curve
from .mcp_server import handle_request, serve_stdio
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
    verdict_for,
)
from .persistence import (
    bundle_from_dict,
    certificate_from_content,
    dossier_from_dict,
)
from .query import ReprolithQuery
from .reconstruction import (
    ModelOrigin,
    NonReconstructable,
    RecipeStep,
    ReconstructionBundle,
    close_gap,
)
from .render import claim_counts, gap_items, render_badge, render_human, render_machine
from .revision import DossierHistory, DossierRevision, dossier_digest, revise
from .run import (
    advance_to_outcome,
    blocked_certificate,
    certified_from_claims,
    load_claims_dataset,
    run_test_set,
)
from .sbml import build_model_sbml, compare_sbml_to_dossier
from .scope import Scope
from .seed import load_test_set, seed_catalog
from .supersession import CertificateLedger, describe_changes
from .verification import (
    VerificationDecision,
    VerificationItem,
    VerificationQueue,
    certificates_needing_review,
    reverify_dependents,
)

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
    "Claim",
    "ClaimAssessment",
    "ComparisonMethod",
    "Dossier",
    "DossierClaim",
    "DossierHistory",
    "DossierRevision",
    "EnginePin",
    "EngineUnavailable",
    "Equation",
    "ExtractionConfidence",
    "Fault",
    "FbaUnavailable",
    "InfeasibleFba",
    "FailureMode",
    "Gap",
    "GapKind",
    "GroundTruth",
    "Identifiers",
    "IllegalTransition",
    "LifecycleState",
    "LintResult",
    "ModelArtifact",
    "ModelClass",
    "ModelOrigin",
    "NonFiniteSimulation",
    "NonReconstructable",
    "OverallVerdict",
    "Parameter",
    "PaperIdentity",
    "RecipeStep",
    "ReconstructionBundle",
    "ReferenceKind",
    "ReproductionLevel",
    "ReprolithQuery",
    "RunMetadata",
    "Scope",
    "Tolerance",
    "ToleranceSource",
    "Transition",
    "Verdict",
    "VerificationDecision",
    "VerificationItem",
    "VerificationQueue",
    "advance_to_outcome",
    "blocked_certificate",
    "build_agreement_report",
    "build_certificate",
    "build_model_sbml",
    "bundle_from_dict",
    "canonical_bytes",
    "canonical_json",
    "certificate_digest",
    "certificate_from_content",
    "certificates_needing_review",
    "certified_from_claims",
    "certify_model",
    "claim_counts",
    "close_gap",
    "compare_sbml_to_dossier",
    "content_hash",
    "default_tolerance",
    "derive_overall",
    "describe_changes",
    "dossier_digest",
    "dossier_from_dict",
    "engine_pin",
    "estimate_difficulty",
    "engine_version",
    "essentiality_agreement",
    "flux_variability",
    "gap_items",
    "handle_request",
    "ingest_sbml",
    "judge_curve",
    "judge_flux",
    "judge_objective",
    "judge_scalar",
    "lint_curve",
    "load_claims_dataset",
    "load_test_set",
    "normalized_curve_distance",
    "not_evaluable",
    "relative_error",
    "render_badge",
    "render_human",
    "render_machine",
    "reverify_dependents",
    "revise",
    "run_test_set",
    "same_modulo_run_metadata",
    "serve_stdio",
    "seed_catalog",
    "simulate",
    "reaction_essentiality",
    "solve_objective",
    "verdict_for",
    "__version__",
]
