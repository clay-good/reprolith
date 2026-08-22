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

import time
from typing import Any

from .agreement import summarize_report
from .catalog import Catalog, CatalogEntry, Identifiers
from .determinism import certificate_digest
from .enums import LifecycleState, ModelClass, ReproductionLevel, Verdict
from .model import Certificate
from .presubmission import presubmission_report
from .render import claim_counts, gap_items
from .supersession import CertificateLedger


def _label_basis(report: dict[str, Any]) -> str:
    """What a class's agreement number can and cannot establish, derived from its own labels.

    A class whose entries all carry one and the same label cannot be scored for discriminative
    skill — "always answer <that label>" scores 100% — so its number establishes agreement with
    an independent implementation and the discipline of abstaining, and nothing about telling
    reproducible work from irreproducible work. Reading it as the latter is the misreading the
    dataset caveats warn about, so the number does not travel without this line attached.
    """
    expected = {key.partition("->")[0] for key in report.get("confusion", {})}
    if len(expected) <= 1:
        return (
            "every labelled entry in this class carries one and the same verdict, so this number "
            "establishes agreement with an independent implementation and abstention discipline "
            "— not the "
            "ability to tell a reproducible result from an irreproducible one"
        )
    return (
        "the labels in this class are not all one verdict; read the dataset's own caveat for how "
        "they were assigned before reading this number as discriminative skill"
    )


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
    published: dict[str, dict[str, Any]] = {}
    for model_class, report in agreement_reports.items():
        # `agreement_rate` counts an abstention as a disagreement, so PK/PD's 30 honest
        # abstentions publish as a rate of 0.0 — the one reading the whole track record exists
        # to prevent. The split replaces it, per class and not only in the total.
        entry = {k: v for k, v in report.items() if k not in ("per_entry", "agreement_rate")}
        entry.update(summarize_report(report))
        entry["label_basis"] = _label_basis(report)
        published[model_class] = entry
    agreement_reports = published
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


    @property
    def ledger(self) -> CertificateLedger:
        """The certificate ledger this surface reads.

        Exposed read-only so a long-lived server can refresh it: the ledger is loaded once at
        start-up, and supersession is expressed by *adding* a file, so a correction published after
        start-up was invisible and `record_result` wrote the retracted verdict into the entry's
        permanent history.
        """
        return self._ledger

    def list_catalog(
        self,
        *,
        model_class: ModelClass | None = None,
        state: LifecycleState | None = None,
    ) -> list[dict[str, Any]]:
        """Browse catalog entries as blind public views, optionally filtered.

        The filters are typed, and compared by equality rather than identity. Annotated `object`
        and compared with `is`, a caller passing the string `"logical"` — which compares equal to
        `ModelClass.LOGICAL`, these being str enums — got an empty list rather than an error: a
        read surface answering "there are none" for a question it did not understand.
        """
        out: list[dict[str, Any]] = []
        for entry in self._catalog.entries:
            if model_class is not None and entry.model_class != model_class:
                continue
            if state is not None and entry.state != state:
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

    def backlog_health(self, at: float | None = None) -> dict[str, Any]:
        """Report backlog depth by state, class, and difficulty, and the labelled mix.

        ``at`` is the time leases are judged against, defaulting to now. It used to default to the
        catalog's own ``at=0.0``, which is before every real lease timestamp — so an expired lease
        still counted as blocking and "claimable now" under-reported work the effectful surface
        would hand out on the very next request, permanently, since leases persist.
        """
        return self._catalog.backlog_health(time.time() if at is None else at)

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
        any assumption-qualified claims, the inescapable scope flag, and ``superseded_by`` — the
        digest of the correction that replaced this certificate, when there is one, so a stale
        verdict never travels as the current answer.
        """
        cert = self._ledger.get(digest)
        if cert is None:
            return None
        view = self._verdict_view(cert)
        view["superseded_by"] = self.superseded_by(digest)
        return view

    def gaps(self, digest: str) -> dict[str, Any] | None:
        """The structured "what was missing" report for a digest, or ``None``.

        Returned wrapped rather than as a bare list, because each gap item carries its claim's
        verdict, and this surface promises that no verdict leaves it without the scope flag beside
        it. A caller reading `"verdict": "reproduced"` off a gap item was reading a verdict with
        nothing qualifying it.
        """
        cert = self._ledger.get(digest)
        if cert is None:
            return None
        return {
            "gaps": gap_items(cert),
            "scope": cert.scope.to_dict(),
            "superseded_by": self.superseded_by(digest),
        }

    def presubmission(self, digest: str) -> dict[str, Any] | None:
        """The author-facing pre-submission report for a digest, or ``None``.

        Re-presents the certificate as a readiness signal plus a prioritized fix list for an
        author to run on their own model before publishing (spec: ``presubmission-check``). It
        recomputes no verdict — the report is derived from the stored certificate.

        Carries ``superseded_by`` for the same reason :meth:`verdict` does, and with more at stake:
        this report says "ready to submit", and a certificate that has since been corrected must
        not be what an author acts on.
        """
        cert = self._ledger.get(digest)
        if cert is None:
            return None
        report = presubmission_report(cert)
        report["superseded_by"] = self.superseded_by(digest)
        return report

    def certificates_for(
        self,
        *,
        title: str | None = None,
        doi: str | None = None,
        pubmed_id: str | None = None,
        accession: str | None = None,
    ) -> list[str]:
        """Digests of every certificate issued for a paper, newest certification first.

        An ``accession`` is resolved through the catalog first: a certificate is keyed by the
        paper's title/doi/pubmed and carries no accession, so matching one directly would always
        come back empty — silently reporting "no certificates" for a paper that has one.

        Heads are ordered by how far down a supersession chain they sit, deepest first, rather
        than by whatever order the ledger happens to hold them in. Insertion order is arbitrary
        (loading a directory sorts by digest filename), and two situations put more than one head
        in the list: a diamond, and a chain whose middle link was never published — in which case
        the superseded root looks like a head, because nothing in the ledger says otherwise. With
        arbitrary order, position 0 could be a superseded verdict while the current one sat below
        it, under a heading that promises newest first.
        """
        if accession is not None and not (title or doi or pubmed_id):
            entry = self._catalog.find(Identifiers(title="", accession=accession))
            if entry is None:
                return []
            ids = entry.identifiers
            title, doi, pubmed_id = ids.title, ids.doi, ids.pubmed_id
        wanted = Identifiers(title=title or "", doi=doi, pubmed_id=pubmed_id)
        keys = wanted.keys()
        matched = {
            digest: cert
            for digest, cert in self._ledger.items()
            if self._paper_keys(cert).intersection(keys)
        }
        superseded = {c.supersedes for c in matched.values() if c.supersedes is not None}
        heads = [(d, c) for d, c in matched.items() if d not in superseded]
        heads.sort(key=lambda item: -self._lineage_depth(item[1]))
        ordered: list[str] = []
        for _, cert in heads:
            for link in self._ledger.chain(cert):
                digest = certificate_digest(link)
                if digest in matched and digest not in ordered:
                    ordered.append(digest)
        return ordered

    def _lineage_depth(self, cert: Certificate) -> int:
        """How deep this certificate's lineage runs, counting a link the ledger does not hold.

        A chain whose middle was never published truncates, so length alone cannot separate the
        current certificate from the superseded root it appears to sit beside: both walk one step.
        Counting the unresolved link puts the deeper lineage first, which is the one a reader means
        by "newest".
        """
        lineage = self._ledger.chain(cert)
        oldest = lineage[-1]
        return len(lineage) + (1 if oldest.supersedes is not None else 0)

    def superseded_by(self, digest: str) -> str | None:
        """The digest of the certificate that supersedes this one, or ``None`` if it is current.

        A certificate records the one it supersedes, but nothing in the stored content points
        forward — so a reader holding a digest (the identity the project asks people to cite) had
        no way to learn that a correction had since flipped the verdict. The ledger holds every
        link needed to answer it, so every certificate view carries it.
        """
        for other_digest, cert in self._ledger.items():
            if cert.supersedes == digest:
                return other_digest
        return None

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
            # An estimation-level pass is a re-fit that recovered the paper's number, not a
            # simulation that reproduced its result — derive_overall deliberately does not consult
            # the level, so without this the summary's three fields read as a clean simulation
            # pass while every other rendering (badge, human render, pre-submission) flags it.
            "estimation_claims": [
                a.claim_id
                for a in cert.assessments
                if a.level is ReproductionLevel.ESTIMATION and a.verdict is not Verdict.FAILED
            ],
            # A gap note that never became a claim is a published result nobody evaluated, and
            # derive_overall reads only the claims — so a certificate can total up to an
            # unqualified "reproduced" while its own "what was missing" report is non-empty. The
            # human certificate and the pre-submission report both print it; this summary carried
            # the verdict without it. Same structural hole as estimation_claims, same fix.
            "gap_notes": list(cert.gap_report),
            "scope": cert.scope.to_dict(),
        }

    def _certificate_view(self, cert: Certificate) -> dict[str, Any]:
        view = cert.content()
        view["verdict"] = self._verdict_view(cert)
        view["gaps"] = gap_items(cert)
        view["superseded_by"] = self.superseded_by(certificate_digest(cert))
        return view

    @staticmethod
    def _paper_keys(cert: Certificate) -> frozenset[tuple[str, str]]:
        p = cert.paper
        return Identifiers(title=p.title, doi=p.doi, pubmed_id=p.pubmed_id).keys()


__all__ = ["ReprolithQuery", "self_validation_summary"]
