"""Reprolith — auto-reproduction & certification engine for the biomedical modeling literature.

This is the engine skeleton: the domain shapes a certificate is built from, the rule
that derives its verdict, the inescapable scope statement, and the determinism harness
that makes a certificate byte-reproducible. The ingestion, reconstruction, and
simulation-oracle stages described in ``openspec/`` build on top of these shapes.
"""

from __future__ import annotations

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
from .query import ReprolithQuery
from .render import claim_counts, gap_items, render_human, render_machine
from .scope import Scope
from .supersession import CertificateLedger, describe_changes

__version__ = "0.0.1"

__all__ = [
    "Assumption",
    "BlindEntry",
    "Catalog",
    "CatalogEntry",
    "CertificateLedger",
    "Certificate",
    "ClaimAssessment",
    "EnginePin",
    "GroundTruth",
    "Identifiers",
    "IllegalTransition",
    "LifecycleState",
    "ModelClass",
    "OverallVerdict",
    "PaperIdentity",
    "ReproductionLevel",
    "ReprolithQuery",
    "RunMetadata",
    "Scope",
    "Transition",
    "Verdict",
    "build_certificate",
    "canonical_bytes",
    "canonical_json",
    "certificate_digest",
    "claim_counts",
    "content_hash",
    "derive_overall",
    "describe_changes",
    "gap_items",
    "render_human",
    "render_machine",
    "same_modulo_run_metadata",
    "__version__",
]
