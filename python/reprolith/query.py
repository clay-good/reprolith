"""The read-only, agent-facing query surface (bootstrap tasks 6.1, 6.3).

This is the read model an MCP server exposes: browse the catalog, get a paper's status,
fetch a certificate, and list its gaps — all side-effect-free and safe to call repeatedly
(spec: ``mcp-server`` — "Read-only and effectful tools are separated"). Two honesty
guarantees are built in:

* every verdict returned carries its scope flag and qualifications — the surface has no
  method that returns a bare reproduced/not boolean (spec: "Scope flag is inescapable over
  MCP too"); and
* catalog reads return the blind entry view, so a ground-truth label never leaves the
  catalog through this surface.

The surface computes no verdict of its own: it reads the ``Certificate`` objects the core
engine produced, so it can never diverge from the repository (spec: "Parity with the human
surface"). The transport binding (the actual MCP tool definitions) wraps this read model.
"""

from __future__ import annotations

from typing import Any

from .catalog import Catalog, CatalogEntry, Identifiers
from .determinism import certificate_digest
from .model import Certificate
from .render import claim_counts, gap_items
from .supersession import CertificateLedger


class ReprolithQuery:
    """A read-only view over a catalog and a certificate ledger.

    Every method returns data and changes nothing. Construct it around the same catalog and
    ledger the core engine writes to, so the surface and the repository never disagree.
    """

    def __init__(self, catalog: Catalog, ledger: CertificateLedger) -> None:
        self._catalog = catalog
        self._ledger = ledger

    # --- catalog / status (blind: no ground-truth label leaves the catalog) --------

    def list_catalog(
        self,
        *,
        model_class: object | None = None,
        state: object | None = None,
    ) -> list[dict[str, Any]]:
        """Browse catalog entries as blind public views, optionally filtered."""
        out: list[dict[str, Any]] = []
        for entry in self._catalog.entries:
            if model_class is not None and entry.model_class is not model_class:
                continue
            if state is not None and entry.state is not state:
                continue
            out.append(self._entry_view(entry))
        return out

    def status(
        self,
        *,
        title: str | None = None,
        doi: str | None = None,
        pubmed_id: str | None = None,
        accession: str | None = None,
    ) -> dict[str, Any] | None:
        """A paper's lifecycle status and recorded history, or ``None`` if unknown."""
        entry = self._catalog.find(
            Identifiers(title=title or "", doi=doi, pubmed_id=pubmed_id, accession=accession)
        )
        return self._entry_view(entry) if entry is not None else None

    # --- certificates / verdicts (scope always travels) ----------------------------

    def certificate(self, digest: str) -> dict[str, Any] | None:
        """The full certificate for a digest: content, verdicts, scope, and gaps."""
        cert = self._ledger.get(digest)
        return self._certificate_view(cert) if cert is not None else None

    def verdict(self, digest: str) -> dict[str, Any] | None:
        """The scope-qualified verdict for a digest — never a bare boolean.

        Returns the overall verdict, per-claim verdicts, per-verdict counts, the names of
        any assumption-qualified claims, and the inescapable scope flag, as one object.
        """
        cert = self._ledger.get(digest)
        return self._verdict_view(cert) if cert is not None else None

    def gaps(self, digest: str) -> list[dict[str, Any]] | None:
        """The structured "what was missing" report for a digest, or ``None``."""
        cert = self._ledger.get(digest)
        return gap_items(cert) if cert is not None else None

    def certificates_for(
        self,
        *,
        title: str | None = None,
        doi: str | None = None,
        pubmed_id: str | None = None,
        accession: str | None = None,
    ) -> list[str]:
        """Digests of every certificate issued for a paper, newest certification first."""
        wanted = Identifiers(title=title or "", doi=doi, pubmed_id=pubmed_id, accession=accession)
        keys = wanted.keys()
        matched = {
            digest: cert
            for digest, cert in self._ledger.items()
            if self._paper_keys(cert).intersection(keys)
        }
        superseded = {c.supersedes for c in matched.values() if c.supersedes is not None}
        # A head is a matched certificate nothing else supersedes; walk each head's chain
        # (newest first) and keep the digests that belong to this paper.
        ordered: list[str] = []
        for head_digest, cert in matched.items():
            if head_digest in superseded:
                continue
            for link in self._ledger.chain(cert):
                digest = certificate_digest(link)
                if digest in matched and digest not in ordered:
                    ordered.append(digest)
        return ordered

    # --- internal view builders (single source: the stored Certificate) ------------

    @staticmethod
    def _entry_view(entry: CatalogEntry) -> dict[str, Any]:
        view = entry.blind().to_dict()
        view["history"] = [t.to_dict() for t in entry.history]
        return view

    @staticmethod
    def _verdict_view(cert: Certificate) -> dict[str, Any]:
        return {
            "overall": cert.overall.value,
            "claim_counts": claim_counts(cert),
            "claims": [a.to_dict() for a in cert.assessments],
            "assumption_qualified_claims": [
                a.claim_id for a in cert.assessments if a.assumption_qualified
            ],
            "scope": cert.scope.to_dict(),
        }

    def _certificate_view(self, cert: Certificate) -> dict[str, Any]:
        view = cert.content()
        view["verdict"] = self._verdict_view(cert)
        view["gaps"] = gap_items(cert)
        return view

    @staticmethod
    def _paper_keys(cert: Certificate) -> frozenset[tuple[str, str]]:
        p = cert.paper
        return Identifiers(title=p.title, doi=p.doi, pubmed_id=p.pubmed_id).keys()


__all__ = ["ReprolithQuery"]
