"""Reprolith — auto-reproduction & certification engine for the biomedical modeling literature.

This is the engine skeleton: the domain shapes a certificate is built from, the rule
that derives its verdict, the inescapable scope statement, and the determinism harness
that makes a certificate byte-reproducible. The ingestion, reconstruction, and
simulation-oracle stages described in ``openspec/`` build on top of these shapes.
"""

from __future__ import annotations

from .canonical import canonical_bytes, canonical_json, content_hash
from .certificate import build_certificate, derive_overall
from .determinism import certificate_digest, same_modulo_run_metadata
from .enums import OverallVerdict, ReproductionLevel, Verdict
from .model import (
    Assumption,
    Certificate,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    RunMetadata,
)
from .scope import Scope

__version__ = "0.0.1"

__all__ = [
    "Assumption",
    "Certificate",
    "ClaimAssessment",
    "EnginePin",
    "OverallVerdict",
    "PaperIdentity",
    "ReproductionLevel",
    "RunMetadata",
    "Scope",
    "Verdict",
    "build_certificate",
    "canonical_bytes",
    "canonical_json",
    "certificate_digest",
    "content_hash",
    "derive_overall",
    "same_modulo_run_metadata",
    "__version__",
]
