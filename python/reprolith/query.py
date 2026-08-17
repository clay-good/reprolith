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

from .agreement import summarize_report
from .catalog import Catalog, CatalogEntry, Identifiers
from .determinism import certificate_digest
from .model import Certificate
from .presubmission import presubmission_report
from .render import claim_counts, gap_items
from .supersession import CertificateLedger


def self_validation_summary(agreement_reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The blind self-validation track record from per-class committed agreement reports.

    Pure function of the reports, so it can be built without loading the certificate ledger (the
    registry builder uses it directly). ``overall`` splits the labelled entries into matched /
    abstentions / other via :func:`reprolith.agreement.summarize_report`, which never counts an
    abstention as a wrong verdict. The three partition ``labelled_entries`` exactly.

    ``by_class`` carries each report's aggregate numbers but **not** its ``per_entry`` rows. Those
    rows pair an accession with its ground-truth label, and the same accessions sit in the live
    work queue — so publishing them here would hand a reproducing agent the answer key for the
    paper it is about to work on, defeating the blind protocol the whole track record rests on.
    The rows stay in the committed report files, where a reviewer auditing the record can read
    them; they do not travel over the agent-facing surfaces.
    """
    agreement_reports = {
        model_class: {k: v for k, v in report.items() if k != "per_entry"}
        for model_class, report in agreement_reports.items()
    }
    splits = [summarize_report(r) for r in agreement_reports.values()]
    agreements = sum(s["matched"] for s in splits)
    total = sum(s["total"] for s in splits)
    abstentions = sum(s["abstained"] for s in splits)
    return {
        "by_class": agreement_reports,
        "overall": {
            "classes": len(agreement_reports),
            "labelled_entries": total,
            "agreements": agreements,
            "abstentions": abstentions,
            "other_disagreements": total - agreements - abstentions,
        },
    }


class ReprolithQuery:
    """A read-only view over a catalog and a certificate ledger.

    Every method returns data and changes nothing. Construct it around the same catalog and
    ledger the core engine writes to, so the surface and the repository never disagree.
    """

    def __init__(
        self,
        catalog: Catalog,
        ledger: CertificateLedger,
        dossiers: dict[str, dict[str, Any]] | None = None,
        bundles: dict[str, dict[str, Any]] | None = None,
        agreement_reports: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._catalog = catalog
        self._ledger = ledger
        # Ingested dossiers and reconstruction bundles keyed by entry accession, so an agent can
        # inspect the model structure Reprolith extracted and how it reconstructed it (design
        # goal 3). Empty when none are loaded.
        self._dossiers = dossiers or {}
        self._bundles = bundles or {}
        # Per-class blind self-validation reports keyed by model-class label — how each class's
        # verdicts matched independently-established ground truth. Empty when none are loaded.
        self._agreement_reports = agreement_reports or {}

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
        """A paper's lifecycle status, recorded history, and any certificate digests, or ``None``.

        Resolving an entry (by accession from the catalog listing, say) and then finding its
        certificates would otherwise be a dead end — an entry carries an accession but a
        certificate is keyed by the paper's title/doi/pubmed. So the view includes
        ``certificates``: the digests issued for this paper, newest first, bridging catalog
        browsing to the certificate a reader actually wants.
        """
        entry = self._catalog.find(
            Identifiers(title=title or "", doi=doi, pubmed_id=pubmed_id, accession=accession)
        )
        if entry is None:
            return None
        view = self._entry_view(entry)
        ids = entry.identifiers
        view["certificates"] = self.certificates_for(
            title=ids.title, doi=ids.doi, pubmed_id=ids.pubmed_id
        )
        return view

    def backlog_health(self) -> dict[str, Any]:
        """Report backlog depth by state, class, and difficulty, and the labelled mix."""
        return self._catalog.backlog_health()

    def self_validation(self) -> dict[str, Any]:
        """Reprolith's blind self-validation track record, per model class and overall.

        ``by_class`` is each class's committed agreement report verbatim — how its blind verdicts
        matched independently-established ground truth (rate, counts, confusion matrix, per-entry
        detail). ``overall`` splits the labelled entries three honest ways rather than as a single
        blended rate, because a blended rate would misrepresent the discipline (spec: ``mcp-server``
        — "An abstention is never counted as a wrong verdict"): a verdict that
        *abstained* (``blocked`` — "insufficient information") is counted apart from one that
        confidently differed from the label. So the PK/PD run's 30 honest abstentions are never
        lumped in with a wrong verdict. ``other_disagreements`` are the remaining confident
        differences (e.g. a qualified ``partially-reproduced`` where the label said ``reproduced``);
        read the confusion matrices for their structure. Empty ``by_class`` when none are loaded.
        """
        return self_validation_summary(self._agreement_reports)

    def dossier(self, accession: str) -> dict[str, Any] | None:
        """The ingested dossier for an entry accession — its extracted model structure."""
        return self._dossiers.get(accession)

    def bundle(self, accession: str) -> dict[str, Any] | None:
        """The reconstruction bundle for an entry accession — the model, recipe, and assumptions."""
        return self._bundles.get(accession)

    # --- certificates / verdicts (scope always travels) ----------------------------

    def certificate_object(self, digest: str) -> Certificate | None:
        """The stored :class:`~reprolith.model.Certificate` for a digest, or ``None``.

        The one place the surface hands back the certificate object rather than a dict view: a
        renderer (the CLI's human certificate) needs the object to run :func:`render_human`
        without reaching into the ledger itself. It still produces no verdict — it returns exactly
        what the engine stored.
        """
        return self._ledger.get(digest)

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

    def presubmission(self, digest: str) -> dict[str, Any] | None:
        """The author-facing pre-submission report for a digest, or ``None``.

        Re-presents the certificate as a readiness signal plus a prioritized fix list for an
        author to run on their own model before publishing (spec: ``presubmission-check``). It
        recomputes no verdict — the report is derived from the stored certificate.
        """
        cert = self._ledger.get(digest)
        return presubmission_report(cert) if cert is not None else None

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


__all__ = ["ReprolithQuery", "self_validation_summary"]
