"""The author-facing pre-submission check (spec: ``presubmission-check``; roadmap #10).

The adoption flywheel: the same reproduction engine, re-presented so an author runs it on their
*own* model before publishing. This module introduces no new oracle — it consumes a
:class:`~reprolith.model.Certificate` the engine already produced and re-frames it for the author
as a readiness signal plus a prioritized "fix this before you submit" list.

Two honesty properties are inherited, not re-derived: the per-claim and overall verdicts and the
scope statement come straight from the certificate (:func:`presubmission_report` never recomputes
a verdict), and the ready-to-submit signal is green only for an unqualified full *simulation*
reproduction, so a partial, assumption-qualified, or estimation-level result can never look ready.
"""

from __future__ import annotations

import os
import posixpath
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from .enums import OverallVerdict, Verdict
from .ingest import UNSTATED_UNIT
from .manuscript_values import model_time_unit
from .model import Certificate
from .oracle import ComparisonMethod, Fault, figure_band_widening
from .render import claims_in_paper, estimation_claims, is_figure_read, unattempted_claims

if TYPE_CHECKING:  # a type-only import: the archive check takes claims, it does not build them
    from .certify import Claim

# Impact buckets for the fix list, most urgent first. A claim a reproducer cannot even evaluate
# outranks a wrong one; a wrong one outranks a partial; a load-bearing value the author left for
# the engine to assume outranks a certificate-level note (spec: "Gaps are ordered by impact").
_CLAIM_PRIORITY = {
    Verdict.NOT_EVALUABLE: 1,
    Verdict.FAILED: 2,
    Verdict.PARTIAL: 3,
}
_LEVEL_PRIORITY = 4
_ASSUMPTION_PRIORITY = 5
_NOTE_PRIORITY = 6

_READINESS = {
    OverallVerdict.REPRODUCED: (
        "Ready to submit: every claim reproduces cleanly under the pinned engine."
    ),
    OverallVerdict.PARTIALLY_REPRODUCED: (
        "Not yet ready: some claims are partial or rest on values Reprolith had to assume. "
        "Address the fix list before submitting."
    ),
    OverallVerdict.NOT_REPRODUCED: (
        "Not ready: no claim reproduces as stated. The fix list shows what a reproducer will hit."
    ),
    OverallVerdict.BLOCKED: (
        "Not ready: nothing is evaluable yet — a reproducer cannot check any claim. Supply the "
        "missing inputs in the fix list."
    ),
}

# Every claim reproduced, but something else withholds a clean pass — a recorded gap, or a claim
# reproduced at estimation level rather than by simulation. The verdict alone would read as ready.
_REPRODUCED_BUT_NOT_READY = (
    "Not yet ready: every claim reproduces, but not cleanly — see the fix list for what a "
    "reproducer would still have to supply or re-derive."
)


def _claim_issue_and_fix(assessment: Any) -> tuple[str, str]:
    """Phrase a non-reproducing claim as an author-facing issue and a concrete fix.

    The fix has to be an **instruction**, and it used to be `implicated` — which is by definition
    the element implicated, a noun phrase. Under a heading reading *FIX BEFORE YOU SUBMIT*, an
    author was handed "Table 7's Brain Cmax, which equals plasma's while its AUC24 and Cmean are
    0.80 of plasma's": the finding, restated, with nothing to do about it.

    And it never said whose fault Reprolith thinks it is. That matters most exactly where the
    stakes are highest: an author told to fix a claim needs to know whether the tool believes
    their *model* fell short or their *table* has a typo, and that this is a hypothesis they
    should check rather than a defect they must accept. `Fault` says so in its own docstring —
    "always a hypothesis, never a proven cause" — and this surface never passed it on.
    """
    if assessment.verdict is Verdict.NOT_EVALUABLE:
        issue = "a reproducer cannot evaluate this claim"
        fix = assessment.root_cause or "supply evaluable output or digitizable reference data"
        return issue, fix
    issue = assessment.discrepancy or f"{assessment.verdict.value} reproduction"
    implicated = (assessment.implicated or "").strip()
    fault = (assessment.fault_hypothesis or "").strip()
    if fault == Fault.MANUSCRIPT.value and implicated:
        fix = (
            f"check {implicated} — Reprolith's hypothesis is that the reported value is wrong "
            "rather than the model, so confirm it against your own run before changing anything"
        )
    elif fault == Fault.RECONSTRUCTION.value and implicated:
        fix = (
            f"reconcile the model with what your paper reports: {implicated}. Reprolith's "
            "hypothesis is that the shipped model, not the reported value, is what falls short"
        )
    else:
        fix = (
            implicated
            or assessment.root_cause
            or "reconcile the reconstructed output with the reported value within tolerance"
        )
    return issue, fix


def _figure_reading_consequence(method: str | None) -> str:
    """What a figure-read claim cost this author, with the real multiplier for their comparison.

    "A band twice as wide" is true of a curve and wrong about the other two — a scalar's figure
    band is three times a printed number's, a distribution band's is 1.67 times — and this is an
    author-facing sentence, so it says the number their claim was actually judged under. A method
    with no widened default says so in words rather than inventing a ratio.
    """
    widening: float | None = None
    if method is not None:
        try:
            widening = figure_band_widening(ComparisonMethod(method))
        except ValueError:
            widening = None  # a method this build does not know: describe it without a number
    band = (
        # Three significant figures: `:g` renders the distribution band's 5/3 as 1.66667,
        # which is not a sentence to put in front of an author.
        f"in a band {widening:.3g}x as wide as a printed number's"
        if widening is not None
        else "in the wider band a reading is judged in"
    )
    return (
        f"judged against values read off your figure, {band} — not against a number you published"
    )


def presubmission_report(cert: Certificate) -> dict[str, Any]:
    """An author-facing pre-submission report derived from a certificate.

    Returns the readiness signal, the certificate's own per-claim and overall verdicts, a
    prioritized fix list (impact order: not-evaluable, failed, partial claims, then load-bearing
    assumptions the author should state, then certificate-level notes), and the inescapable scope
    statement. A fully reproduced certificate yields an empty fix list.
    """
    # A gap report is a record of something the artifact did not state, so a certificate carrying
    # one is not ready however clean its verdicts read — otherwise the report says READY TO SUBMIT
    # above a list of things to fix first, which is the promise in this docstring broken out loud.
    # An estimation-level claim is the same kind of overstatement: re-fitting a parameter from data
    # is a weaker result than running the described model, so "every claim reproduces cleanly under
    # the pinned engine" is not something this report may say about it.
    # And a claim nobody could evaluate is the fix list's own priority 1, so a report that ranks it
    # first while announcing "every claim reproduces cleanly" contradicts itself in two lines. The
    # overall rule drops abstentions before deciding, by design, so `reproduced` does not imply
    # every claim was judged — this report has to look for itself.
    estimation = estimation_claims(cert)
    ready = (
        cert.overall is OverallVerdict.REPRODUCED
        and not any(a.assumption_qualified for a in cert.assessments)
        and not any(a.verdict is Verdict.NOT_EVALUABLE for a in cert.assessments)
        and not cert.gap_report
        and not estimation
    )

    actions: list[dict[str, Any]] = []
    # A claim that reproduced *only* under a value Reprolith supplied is a reason the clean pass
    # was withheld, so the fix list has to say so. One row, not one per claim: an assumption is a
    # value, not a claim, and on the metformin certificate the per-claim form emitted twenty-three
    # rows carrying the identical sentence — "state the value this claim rests on", naming no value
    # — at the same priority as the one row that names it. The single fix an author can act on was
    # the twenty-fourth of twenty-four items. Which claim rests on which assumption is not recorded
    # per claim, so the rows could not have said it even one at a time; the claims they covered are
    # carried here instead, where they can be read at once.
    qualified = [
        a for a in cert.assessments
        if a.verdict is Verdict.REPRODUCED and a.assumption_qualified
    ]
    for a in cert.assessments:
        if a.verdict is Verdict.REPRODUCED:
            continue
        issue, fix = _claim_issue_and_fix(a)
        actions.append(
            {
                "priority": _CLAIM_PRIORITY[a.verdict],
                "kind": "claim",
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "source_location": a.source_location,
                "issue": issue,
                "fix": fix,
            }
        )
    for claim_id in estimation:
        a = next(x for x in cert.assessments if x.claim_id == claim_id)
        if a.verdict is not Verdict.REPRODUCED:
            continue  # already in the fix list with its own shortfall
        actions.append(
            {
                "priority": _LEVEL_PRIORITY,
                "kind": "level",
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "source_location": a.source_location,
                "issue": "this claim was reproduced by re-fitting parameters, not by running the "
                         "described model",
                "fix": "state the parameter values and conditions needed to simulate this claim "
                       "directly, so a reproducer need not re-fit it",
            }
        )
    for asm in cert.assumptions:
        # An assumption awaiting expert confirmation withholds the clean pass exactly as a
        # load-bearing one does (derive_overall consults both), so it belongs on the fix list too.
        # The sibling gap report already listed it; this one skipped it.
        if not asm.load_bearing and not asm.verification_item:
            continue
        issue = (
            f"Reprolith had to assume a load-bearing value: {asm.chosen}"
            if asm.load_bearing
            else f"this assumption is awaiting expert confirmation ({asm.verification_item}): "
                 f"{asm.chosen}"
        )
        actions.append(
            {
                "priority": _ASSUMPTION_PRIORITY,
                "kind": "assumption",
                "claim_id": None,
                "quantity": asm.description,
                "source_location": None,
                "issue": issue,
                # `basis` is why Reprolith had to assume it — and for some assumptions it is also
                # the reason the author cannot discharge the item at all: the spatial engine
                # implements one boundary condition and the stochastic class samples an ensemble,
                # so six of the thirty published certificates carried an instruction no wording in
                # any paper could satisfy. The sibling `gaps` report prints the basis; this one,
                # the surface that exists to be acted on, dropped it. An item the author cannot
                # close now says so instead of asking them to try.
                "why": asm.basis,
                "fix": (
                    f"state {asm.description} explicitly so it need not be assumed"
                    if asm.author_can_close
                    else (
                        "nothing in the paper can clear this one — it is a limit of Reprolith's "
                        f"engine, not an omission in the paper: {asm.basis}. If that does not "
                        "describe the model, this result is not evidence about it"
                    )
                ),
            }
        )
    for note in cert.gap_report:
        actions.append(
            {
                "priority": _NOTE_PRIORITY,
                "kind": "note",
                "claim_id": None,
                "quantity": None,
                "source_location": None,
                "issue": note,
                # Not the note again. Under a heading reading *FIX BEFORE YOU SUBMIT*, this row
                # printed the finding on one line and the identical sentence as its fix on the
                # next — the shape `_claim_issue_and_fix` was already corrected for once, still
                # standing here. Every entry in a gap report is something the artifact or the paper
                # does not state (`_artifact_gaps` takes only the gaps the artifact does not carry;
                # a blocked run's are the inputs it lacked), so one instruction is true of all of
                # them, and it is the one the author can act on.
                "fix": "state it in your paper or your model file, so a reproducer need not "
                       "infer it",
            }
        )
    # Appended after the named assumptions so that, at the same priority and under a stable sort,
    # an author reads the values they can state before the roll-up of what those values withheld.
    if qualified:
        named = [
            asm for asm in cert.assumptions if asm.load_bearing or asm.verification_item
        ]
        actions.append(
            {
                "priority": _ASSUMPTION_PRIORITY,
                "kind": "assumption",
                "claim_id": None,
                # The claims this covers, so the roll-up loses nothing the rows carried.
                "claims": [a.claim_id for a in qualified],
                "quantity": (
                    f"{len(qualified)} claim(s) that reproduced only under an assumption"
                ),
                "source_location": None,
                "issue": "these reproduced only under an assumption Reprolith supplied, not as a "
                         "clean pass",
                "fix": (
                    "state the assumed values listed above explicitly, so these need not rest on "
                    "them"
                    if named
                    # Nothing above names one: this certificate carries no Assumption object, which
                    # is what the claims-dataset path produces, and then this row is the whole
                    # signal rather than a roll-up of one.
                    else "state the values these claims rest on so they need not be assumed"
                ),
            }
        )
    # Stable, deterministic order: impact bucket first, insertion order (the certificate's claim
    # order) preserved within a bucket by the stable sort.
    actions.sort(key=lambda item: item["priority"])

    return {
        "overall": cert.overall.value,
        "ready_to_submit": ready,
        "readiness": _READINESS[cert.overall] if ready or cert.overall is not OverallVerdict.REPRODUCED
        else _REPRODUCED_BUT_NOT_READY,
        "per_claim": [a.to_dict() for a in cert.assessments],
        # What this check did *not* look at, when a budget chose against it. An author reading
        # "three claims, all clean" about a fourteen-claim paper is reading a true sentence as an
        # answer to a question it did not address, and `per_claim` alone cannot tell them apart.
        # Not a fix — nothing here is theirs to fix — and it gates nothing: `ready_to_submit`
        # already requires an unqualified `reproduced`, which a budgeted certificate never is.
        **(
            {}
            if cert.selection is None
            else {"not_attempted": unattempted_claims(cert), "claims_in_paper": claims_in_paper(cert)}
        ),
        "fix_list": actions,
        # Reported, and deliberately *not* a fix that gates readiness — the same call the archive
        # check makes about `curves_without_values`, one surface over, and for the same reason.
        # Publishing results as figures is what papers do, and an author told NOT READY for it is
        # being told their honest work is broken. An estimation-level pass does gate, because
        # re-fitting answers a *different* question; a figure reading answers the same one in a
        # band twice as wide. What is worth their knowing is the consequence and how cheaply they
        # can remove it, and that is what this says.
        "judged_from_figure_readings": [
            {
                "claim_id": a.claim_id,
                "quantity": a.quantity,
                "source_location": a.source_location,
                "consequence": _figure_reading_consequence(a.method),
                "you_can_remove_it": "publish this curve's values — a table, a supplementary data "
                                     "file, or the SED-ML data set an archive can carry — so it is "
                                     "judged against your numbers rather than a reading of your "
                                     "picture",
            }
            for a in cert.assessments
            if is_figure_read(a.reference_kind)
        ],
        "scope": cert.scope.to_dict(),
    }


def render_presubmission_human(cert: Certificate) -> str:
    """A plain-text pre-submission report an author can act on directly."""
    report = presubmission_report(cert)
    paper = cert.paper
    lines: list[str] = []

    lines.append(f"PRE-SUBMISSION REPRODUCIBILITY CHECK — {paper.title}")
    lines.append("")
    verdict = "READY TO SUBMIT" if report["ready_to_submit"] else "NOT YET READY"
    lines.append(f"{verdict}  (overall: {report['overall']})")
    lines.append(f"  {report['readiness']}")
    lines.append("")

    lines.append("FIX BEFORE YOU SUBMIT (most impactful first)")
    if not report["fix_list"]:
        lines.append("  (nothing — every claim reproduces cleanly)")
    for item in report["fix_list"]:
        where = f"[{item['claim_id']}] {item['quantity']}: " if item["claim_id"] else ""
        if not where and item["quantity"]:
            where = f"{item['quantity']}: "
        source = f" (source {item['source_location']})" if item["source_location"] else ""
        lines.append(f"  - {where}{item['issue']}{source}")
        if item.get("claims"):
            lines.append(f"      claims: {', '.join(item['claims'])}")
        lines.append(f"      fix: {item['fix']}")
    lines.append("")

    # Not under "fix before you submit", because it is not a fix — see the field's own note. It is
    # printed even above a READY TO SUBMIT, because "every claim reproduces cleanly" and "one of
    # them was checked against a reading of your picture" are both true, and the second is the one
    # the author can do something cheap about.
    if report.get("not_attempted"):
        lines.append("NOT CHECKED (a budget chose against these — not a fix, and not your doing)")
        lines.append(
            f"  {len(report['not_attempted'])} of your paper's {report['claims_in_paper']} claims "
            "were never run, so nothing above says anything about them"
        )
        for item in report["not_attempted"]:
            lines.append(f"  - [{item['claim_id']}] {item['quantity']}")
        lines.append("")

    readings = report["judged_from_figure_readings"]
    if readings:
        lines.append("JUDGED FROM A READING OF YOUR FIGURE (not a fix — a consequence)")
        for item in readings:
            lines.append(f"  - [{item['claim_id']}] {item['quantity']}: {item['consequence']}")
            lines.append(f"      you can remove it: {item['you_can_remove_it']}")
        lines.append("")

    lines.append("SCOPE")
    lines.append(f"  {cert.scope.human}")
    return "\n".join(lines)


#: Fix-list priorities for an archive check, in the order an author should act. An archive that
#: cannot be read at all is not on this scale — it has no report to prioritize.
#: Above everything else: a reaction that states no rate is not a defect in what a reproducer
#: checks, it is a defect in whether there is a run to check at all — and the two engines here
#: disagree about which, one refusing the file and one integrating it with that flux at zero.
#: Above the rate-law check, and above everything: a model that does not name its own quantities
#: is not a model with a problem in it. One engine refuses the file and the other runs a different
#: model to completion, so nothing below this is worth an author's attention until it is fixed.
_ARCHIVE_UNNAMED_PRIORITY = -1
_ARCHIVE_NO_RATE_LAW_PRIORITY = 0
_ARCHIVE_MISMATCH_PRIORITY = 1
#: Shares the top tier with an experiment/model mismatch, because they fail the same way: the run
#: completes, produces a plausible number, and nothing says it was not the published one.
_ARCHIVE_MANUSCRIPT_PRIORITY = 1
#: Above "states no targetable claim", because it is a *cause* of one: a data source that could
#: not be read leaves its claim with no reference values, and the two findings are otherwise
#: indistinguishable to the author.
_ARCHIVE_UNREAD_DATA_PRIORITY = 1
_ARCHIVE_NO_CLAIM_PRIORITY = 2
_ARCHIVE_UNADOPTABLE_PRIORITY = 3
_ARCHIVE_GAP_PRIORITY = 4

#: What this check is, said in the report itself. The certificate scope statement is not reusable
#: here: it opens "This certificate attests…", and this check issues no certificate — printing it
#: would put a certificate's words on a report that ran no model and reached no verdict.
_ARCHIVE_NOTE = (
    "This check reads the archive only. It runs no model, reaches no verdict, and issues no "
    "certificate; it says nothing about biological correctness or clinical use."
)



#: What an author does about an element that names no quantity. One sentence, shared by the two
#: places this is reported from — the archive that could not be read and the one that could.
_UNNAMED_FIX = (
    "give every species, parameter, compartment and reaction an id, and every rule the variable "
    "it sets; an element that names no quantity is not a detail your reproducer can work around, "
    "and one of the two engines will publish a curve for it anyway — COPASI refuses the import "
    "with a libSBML error code and a line number, while libRoadRunner runs the file to completion "
    "having invented a binding for each anonymous element, and prints nothing"
)


def _unnamed_declarations_in(
    archive: str | os.PathLike[str] | bytes,
) -> dict[str, tuple[str, ...]]:
    """Every archive member that parses as SBML and does not name what it declares.

    Used on the path where the archive could *not* be ingested, so it cannot ask the manifest
    which member is the model — it tries them all and keeps the ones that parse. A member that is
    not SBML, and an archive that is not even a zip, contribute nothing rather than raising: this
    runs while reporting one failure and must not become a second.
    """
    import zipfile
    from io import BytesIO

    from .export import declarations_without_identifiers

    found: dict[str, tuple[str, ...]] = {}
    try:
        handle = BytesIO(archive) if isinstance(archive, bytes) else archive
        with zipfile.ZipFile(handle) as zf:
            for name in zf.namelist():
                if not name.lower().endswith((".xml", ".sbml")):
                    continue
                try:
                    unnamed = declarations_without_identifiers(zf.read(name).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                if unnamed:
                    found[name] = unnamed
    except (zipfile.BadZipFile, OSError, KeyError):
        return {}
    return found


def archive_report(
    archive: str | os.PathLike[str] | bytes, *, claims: Sequence[Claim] = ()
) -> dict[str, Any]:
    """An author-facing check of a COMBINE archive, before any certificate exists.

    :func:`presubmission_report` answers "given the verdict Reprolith reached, what should I fix?"
    This answers the question that comes before it: an author has an archive on disk and wants to
    know what a reproducer will find in it. No engine runs and nothing is certified — the archive
    is ingested (:func:`reprolith.ingest_omex`), its experiment is compared against its model, and
    its recipes are read for whether they can be adopted verbatim.

    Returns the same shape :func:`presubmission_report` does — a readiness flag, a readiness
    sentence, a prioritized fix list, and the scope statement — plus what was found in the archive.
    An archive that cannot be read at all is reported as not ready with the refusal as its single
    fix item, rather than raising: a malformed archive is the most actionable finding there is.

    The fix list is ordered by what most changes what a reproducer gets:

    1. **A mismatch between the experiment and the model.** The failure is silent — an override
       aimed at a parameter that is not there runs the unmodified model — so it outranks anything
       merely missing.
    2. **No targetable claim.** An archive that states no published result gives a reproducer
       nothing to check; it can be run, but it cannot be reproduced.
    3. **A recipe that cannot be adopted verbatim.** A parameter scan or a modified model means a
       reproducer must reconstruct the run rather than read it.
    4. **Load-bearing gaps** the ingested model leaves open.

    ``claims`` are the paper's own published results — the author has them, and nothing in an
    archive does. Supplied, they add the check the archive cannot make on itself: whether the
    experiment runs what the paper reports (:func:`reprolith.manuscript_mismatches`), which is the
    other top-tier finding, since a document that runs a neighbouring arm produces a plausible
    number and no sign of trouble. Omitted, that check does not run, and the report says so rather
    than letting a clean fix list read as an archive that runs the paper's results.
    """
    from .export import (
        declarations_without_identifiers,
        packages_no_time_course_describes,
        reactions_without_rate_laws,
        sedml_declarations_without_identifiers,
        what_a_package_means,
    )
    from .manuscript import manuscript_mismatches
    from .omex import _normalize, archive_mismatches, ingest_omex
    from .sedml import parse_sedml_recipes, unreadable_data_descriptions

    found: dict[str, Any] = {
        "readable": True,
        "files": [],
        "claims": {"targetable": 0, "figure_referenced": 0, "not_targetable": 0},
        "adoptable_recipes": 0,
        # Zero is not "they all pass": it is "nothing was compared". The renderer says which. It
        # counts what was actually compared, not what the caller handed in — an archive with no
        # experiment compares nothing however many results the author supplies, and a count that
        # said otherwise would be this module's own kind of defect: a number standing in for a
        # check that never ran.
        "manuscript_claims_checked": 0,
        # What the numbers in the experiment's window *mean*. A document that runs 0 to 30 says
        # nothing about 30 of what; only the model does, and a reproducer reading the deposit
        # rather than the paper has nothing else to go on. Reported, never judged — see the
        # metformin deposit, whose declared time unit is a hundred hours.
        "run_time_unit": UNSTATED_UNIT,
    }
    actions: list[dict[str, Any]] = []
    try:
        dossier = ingest_omex(archive, entry="submitted")
    except ValueError as refused:
        found["readable"] = False
        # Before repeating the refusal, ask whether the model names its own quantities — because
        # if it does not, ingestion's message is about Reprolith and not about the author's file.
        # Measured on a model with one unnamed species: the archive came back refused with
        # "parameter name is required", which is this package's dataclass complaining, and names
        # neither the species nor the file it is in. The real fault is one an author can act on
        # and no engine reports (see `declarations_without_identifiers`), so it is said first and
        # the original refusal is carried as the symptom it is.
        unnamed_by_member = _unnamed_declarations_in(archive)
        found["declarations_without_identifiers"] = [
            f"{member}: {name}" for member, names in unnamed_by_member.items() for name in names
        ]
        if unnamed_by_member:
            member, names = next(iter(unnamed_by_member.items()))
            listed = ", ".join(names[:5]) + (" and others" if len(names) > 5 else "")
            issue = (
                f"{len(names)} elements of {member} state no identifier ({listed}), so the model "
                f"does not say which quantities it means; reading it failed with {str(refused)!r}, "
                "which is a symptom of that rather than a separate problem"
            )
            fix = _UNNAMED_FIX
        else:
            issue, member, fix = str(refused), None, (
                "repair the archive so its manifest and its members agree"
            )
        return {
            "ready_to_submit": False,
            "readiness": (
                "this archive cannot be read, so nothing in it can be reproduced: " + issue
            ),
            "found": found,
            "fix_list": [{
                "priority": 0,
                "kind": "unnamed" if unnamed_by_member else "archive",
                "claim_id": None,
                "quantity": None,
                "source_location": member,
                "issue": issue,
                "fix": fix,
            }],
            "note": _ARCHIVE_NOTE,
        }

    found["files"] = [a.to_dict() for a in dossier.artifacts]
    targetable = dossier.targetable_claims()
    found["claims"] = {
        "targetable": len(targetable),
        "figure_referenced": sum(1 for c in targetable if not c.reference_data),
        "not_targetable": len(dossier.claims) - len(targetable),
    }

    experiment = next(
        (a.filename for a in dossier.artifacts if a.detected_format == "sed-ml"), None
    )
    model = next((a.filename for a in dossier.artifacts if a.detected_format == "sbml"), None)
    # Both are needed to compare one against the other, and both lookups are guarded. No archive
    # `ingest_omex` accepts is known to reach this with no sbml-typed artifact — ingestion records
    # the model it read under its own typing, which wins over the manifest's, even for a manifest
    # that types the model `application/xml` (asserted in tests/test_archive_check.py). The guard
    # is defensive: an unguarded `next()` here would surface as a RuntimeError out of a report
    # whose whole purpose is to be readable.
    # What kind of model it is decides which of these questions even apply. A constraint-based
    # model is solved at steady state and a logical one advances in discrete steps, so "ship a
    # SED-ML document whose plots are the curves your paper shows" is advice about a run nobody
    # performs — told to an author whose files may be perfect. The check says what it cannot judge
    # instead of issuing that fix.
    not_a_time_course: tuple[str, ...] = ()
    # Bound before the branch that fills them: the reads below are guarded on `model`, and a name
    # that only exists inside a guard is one short-circuit away from an UnboundLocalError out of a
    # report whose whole purpose is to be readable.
    sedml: str | None = None
    if model is not None:
        import zipfile
        from io import BytesIO

        handle = BytesIO(archive) if isinstance(archive, bytes) else archive
        with zipfile.ZipFile(handle) as zf:
            # `_normalize`, not `lstrip("./")`: lstrip takes a *character set*, so a member named
            # `.hidden.xml` loses its leading dot and no longer matches itself.
            stored = {_normalize(name): name for name in zf.namelist()}
            sbml = zf.read(stored[_normalize(model)]).decode("utf-8")
            sedml = (
                zf.read(stored[_normalize(experiment)]).decode("utf-8")
                if experiment is not None
                else None
            )
        # Before anything about *what* the model says: whether it says which quantities it means.
        # Not gated on the model class — every class's elements need identifiers, and a
        # constraint-based model with an unnamed reaction is as broken as a kinetic one.
        unnamed = declarations_without_identifiers(sbml)
        found["declarations_without_identifiers"] = list(unnamed)
        if unnamed:
            listed = ", ".join(unnamed[:5]) + (" and others" if len(unnamed) > 5 else "")
            actions.append({
                "priority": _ARCHIVE_UNNAMED_PRIORITY, "kind": "unnamed", "claim_id": None,
                "quantity": None, "source_location": model,
                "issue": f"{len(unnamed)} elements of your model state no identifier ({listed}); "
                         "libSBML reports these as errors and still returns the model, so a "
                         "reader that refuses only fatal documents accepts it — and the two "
                         "engines then disagree about what you shipped: COPASI refuses the import "
                         "with a libSBML error code and a line number, while libRoadRunner runs "
                         "the file to completion having invented a binding for each anonymous "
                         "element, and prints nothing",
                "fix": _UNNAMED_FIX,
            })

        not_a_time_course = packages_no_time_course_describes(sbml)
        found["not_a_time_course"] = [
            {"package": package, "means": what_a_package_means(package)}
            for package in not_a_time_course
        ]
        # Only for a model a time course describes: a constraint-based or logical model has no
        # rate laws by construction, and reporting every reaction of one would send an author to
        # repair a file that is already right.
        rate_less = () if not_a_time_course else reactions_without_rate_laws(sbml)
        found["reactions_without_rate_laws"] = list(rate_less)
        if rate_less:
            shown = ", ".join(rate_less[:5]) + (" and others" if len(rate_less) > 5 else "")
            actions.append({
                "priority": _ARCHIVE_NO_RATE_LAW_PRIORITY, "kind": "rate-law", "claim_id": None,
                "quantity": None, "source_location": model,
                "issue": f"{len(rate_less)} of your reactions state no rate law ({shown}); "
                         "reproducers will not agree on what your model does, and none of them "
                         "will be told why — COPASI imports it and then abandons the run partway, "
                         "returning a short trajectory rather than an error, and libRoadRunner "
                         "refuses a kineticLaw whose math is empty but integrates one that is "
                         "simply absent, taking that reaction's rate as zero with nothing printed",
                "fix": "give every reaction a kineticLaw with math in it; a reaction left without "
                       "one is not a slower path through your model, it is a path that is not "
                       "there, and one of the two engines will publish that as your result",
            })

    if experiment is not None and model is not None and sedml is not None:
        # The document's own version of the model's question, and it fails more quietly: a task
        # with no id is not skipped *with a reason*, it is unreachable — every other element refers
        # to a task by id — so the adoptable-run count drops to zero and nothing says which task
        # went missing. Reported before the count, so the count is never the only thing said.
        unnamed_sedml = sedml_declarations_without_identifiers(sedml)
        found["declarations_without_identifiers"] += [
            f"{experiment}: {name}" for name in unnamed_sedml
        ]
        if unnamed_sedml:
            listed = ", ".join(unnamed_sedml[:5]) + (
                " and others" if len(unnamed_sedml) > 5 else ""
            )
            actions.append({
                "priority": _ARCHIVE_UNNAMED_PRIORITY, "kind": "unnamed", "claim_id": None,
                "quantity": None, "source_location": experiment,
                "issue": f"{len(unnamed_sedml)} elements of your experiment state no identifier "
                         f"({listed}); everything in a SED-ML document refers to everything else "
                         "by id, so an element without one cannot be referred to and is simply "
                         "not read — the adoptable-run count below drops without a line anywhere "
                         "saying which run went missing",
                "fix": "give every model, simulation, task, data generator and output in your "
                       "document an id; an element with none is not read at all, and the only "
                       "sign of it is a number that got smaller",
            })

        # The author's own recorded values, and every reason one of them was not read. Each of
        # these used to be a silent skip whose only symptom was a claim with no reference data —
        # which is the same thing the report says about a paper that published no values at all.
        import zipfile as _zipfile
        from io import BytesIO as _BytesIO

        handle = _BytesIO(archive) if isinstance(archive, bytes) else archive
        with _zipfile.ZipFile(handle) as zf:
            members = {
                _normalize(name): zf.read(name).decode("utf-8", errors="replace")
                for name in zf.namelist()
                if name.lower().endswith((".csv", ".tsv", ".txt", ".numl", ".xml"))
            }
        # Keyed the way the document writes its `source`, which is how the reader resolves it.
        unread = unreadable_data_descriptions(
            sedml, {name: text for name, text in members.items()}
        )
        found["unreadable_data_descriptions"] = list(unread)
        for message in unread:
            actions.append({
                "priority": _ARCHIVE_UNREAD_DATA_PRIORITY, "kind": "data", "claim_id": None,
                "quantity": None, "source_location": experiment,
                "issue": f"one of your recorded data series cannot be read — {message}",
                "fix": "a data source that cannot be resolved leaves the claim that cites it with "
                       "no reference values, and nothing downstream can tell that apart from a "
                       "paper that published none; ship the series as CSV, name a source the "
                       "archive contains, and select one column with one slice",
            })

        # Re-read from the archive rather than from the dossier: the dossier keeps what the
        # document *claimed*, and this asks whether the run behind those claims is adoptable.
        recipes = parse_sedml_recipes(sedml)
        found["adoptable_recipes"] = len(recipes)
        try:
            found["run_time_unit"] = model_time_unit(sbml)
        except ValueError:
            pass  # a model that does not parse is reported by the reader, not twice here
        for message in archive_mismatches(sedml, sbml):
            actions.append({
                "priority": _ARCHIVE_MISMATCH_PRIORITY, "kind": "mismatch", "claim_id": None,
                "quantity": None, "source_location": experiment, "issue": message,
                "fix": "make the experiment and the model agree; an override aimed at an element "
                       "that is not there runs the unmodified model and reports nothing",
            })
        found["manuscript_claims_checked"] = len(claims)
        for message in manuscript_mismatches(sedml, sbml, claims):
            actions.append({
                "priority": _ARCHIVE_MANUSCRIPT_PRIORITY, "kind": "manuscript", "claim_id": None,
                "quantity": None, "source_location": experiment, "issue": message,
                "fix": "ship a run that produces the result your paper reports; a document that "
                       "runs a neighbouring arm reproduces a plausible number and flags nothing",
            })
        if targetable and not recipes and not not_a_time_course:
            actions.append({
                "priority": _ARCHIVE_UNADOPTABLE_PRIORITY, "kind": "recipe", "claim_id": None,
                "quantity": None, "source_location": experiment,
                "issue": "the experiment states results but no run a reproducer can adopt "
                         "verbatim (a parameter scan, a modified model, or a window that does "
                         "not start at zero)",
                "fix": "ship a plain uniform time course over the unmodified model for each "
                       "curve you publish, so a reproducer runs what you ran",
            })

    # Reported, and deliberately *not* a fix that gates readiness. Publishing results as figures
    # is what papers do, and a document that plots its curves is a document doing its job — an
    # archive marked NOT READY for it would tell almost every honest author their work is broken.
    # What is true, and worth their knowing, is the consequence: nobody can check those curves
    # without first reading them off the picture, and such a reading is judged in a band twice as
    # wide as a number they print. They are the one person who can remove that step cheaply,
    # because they have the numbers.
    found["curves_without_values"] = [
        {"claim_id": c.id, "quantity": c.quantity, "source_location": c.source_location}
        for c in targetable if not c.reference_data
    ]

    if not targetable and not not_a_time_course:
        # Two archives reach this, and one instruction was written for only one of them. A document
        # with no outputs at all states nothing, and "plot your curves" is the whole answer. A
        # document carrying only **reports** has stated something — a report is an export format,
        # "write these columns", and Reprolith retains its data sets non-targetable on purpose
        # rather than reading them as results the paper staked. Its author was told to plot curves,
        # over columns they had already named, with no acknowledgement that a paper whose results
        # are numbers in a table has nothing SED-ML can say: there is no way to state "the peak of
        # this curve is the published value". The route for that is the one this command already
        # takes, and it went unmentioned exactly where it was the only answer.
        retained = len(dossier.claims) - len(targetable)
        actions.append({
            "priority": _ARCHIVE_NO_CLAIM_PRIORITY, "kind": "claims", "claim_id": None,
            "quantity": None, "source_location": experiment,
            "issue": (
                f"the archive states no published result — its {retained} report data set(s) are "
                "an export format, not a statement that your paper published those values — so a "
                "reproducer can run it but has nothing to check it against"
                if retained
                else "the archive states no published result, so a reproducer can run it but has "
                     "nothing to check it against"
            ),
            "fix": "ship a SED-ML document whose plots are the curves your paper shows; for a "
                   "result your paper prints as a number rather than plots, no document can say "
                   "it — pass your claims file to `reprolith archive-check --claims` instead",
        })

    # Gaps are reported, and deliberately *not* as things for the author to fix. A dossier's
    # load-bearing gaps mix two different findings under one shape: something the archive genuinely
    # omits (45 of metformin's 69 values state no unit) and something Reprolith's extraction cannot
    # represent however fully the archive states it (its 35 reactions, its events). Telling an
    # author to "state this in the archive" covers the first and is simply wrong about the second —
    # it sends them to fix a file that is already correct. Nothing here distinguishes the two, so
    # this says what is true of both and gates readiness on neither.
    found["extraction_gaps"] = [
        {"element": gap.element, "detail": gap.detail} for gap in dossier.load_bearing_gaps()
    ]

    actions.sort(key=lambda item: item["priority"])
    # A model no time course describes cannot come out ready: the questions this check answers
    # about published results are the time-course ones, and they were withheld rather than
    # answered. Green would say a reproducer knows what to check, which nothing here established.
    ready = not actions and not not_a_time_course
    if not_a_time_course:
        readiness = (
            "this check reads a time-course experiment, and this model is "
            + "; ".join(what_a_package_means(package) for package in not_a_time_course)
            + " — so whether it states its published results is not something this judged. What "
            "it could check is above"
        )
    elif ready:
        readiness = (
            "this archive is readable, states its results, and its experiment agrees with its "
            "model"
            + (
                f" and with the {found['manuscript_claims_checked']} result(s) your paper reports"
                if found["manuscript_claims_checked"]
                else " (nothing was compared against your paper's own reported results)"
            )
        )
    else:
        readiness = "a reproducer would hit the items below before reaching a verdict"
    return {
        "ready_to_submit": ready,
        "readiness": readiness,
        "found": found,
        "fix_list": actions,
        "note": _ARCHIVE_NOTE,
    }


def pair_report(
    sedml: str,
    sbml: str,
    *,
    claims: Sequence[Claim] = (),
    data_files: Mapping[str, str] = MappingProxyType({}),
    model_filename: str | None = None,
) -> dict[str, Any]:
    """The same check for a document and a model that are not packaged as an archive.

    Most papers ship the two files loose — BioModels does, and so does this repository — and an
    author should not have to build a COMBINE archive to find out what a reproducer would hit. The
    pair is packaged into the archive those files describe (:func:`reprolith.build_omex_archive`,
    which stores the model where the document's own ``source`` says it is) and that archive is
    checked, so the terminal and the archive path cannot reach different conclusions.

    Two consequences are stated in the report rather than left implicit. The manifest was
    *generated*, so nothing here can find a defect in the author's own manifest — there is none
    yet. And the model is stored where the document's own ``source`` says it is, which means the
    packaging cannot notice that the file supplied has a different name: ``model_filename`` is how
    a caller that knows the name says so, and a disagreement is reported rather than smoothed over,
    because a reproducer following the document looks for the name the document writes.

    ``data_files`` are the data files the document names, keyed by the ``source`` it writes; the
    caller reads them from beside the document. Without them a document that plots shipped values
    reports them as missing, which for a loose pair would be the reader's doing, not the author's.
    """
    from .export import build_omex_archive
    from .sedml import sedml_model_sources

    sources = sedml_model_sources(sedml)
    if len(sources) != 1:
        return _unreadable(
            f"the document runs {len(sources)} model files ({', '.join(sources) or 'none'}); "
            "a check reads one document against the one model it names",
            fix="name exactly one model file in the document",
        )
    try:
        archive = build_omex_archive(
            sbml,
            sedml,
            model_location=sources[0],
            experiment_location="experiment.sedml",
            data_files=data_files,
        )
    except ValueError as refused:
        # One message covers several causes — an unparseable model, a source pointing elsewhere,
        # a location that is not a plain relative path — so the fix names the file the message
        # names rather than asserting which of them it was.
        return _unreadable(str(refused), fix="repair the file this names, or the document that points at it")
    report = archive_report(archive, claims=claims)
    report["found"]["assembled_from_loose_files"] = True
    if model_filename is not None and posixpath.basename(sources[0]) != model_filename:
        report["fix_list"].append({
            "priority": _ARCHIVE_UNADOPTABLE_PRIORITY,
            "kind": "naming", "claim_id": None, "quantity": None,
            "source_location": sources[0],
            "issue": (
                f"the document runs '{sources[0]}', and the model you have is named "
                f"'{model_filename}'; a reproducer follows the document's own source"
            ),
            "fix": "ship the model under the name the document names, or correct the document",
        })
        report["fix_list"].sort(key=lambda item: item["priority"])
        report["ready_to_submit"] = False
        report["readiness"] = "a reproducer would hit the items below before reaching a verdict"
    return report


def _unreadable(issue: str, *, fix: str) -> dict[str, Any]:
    """A report whose single finding is that there was nothing checkable to begin with."""
    return {
        "ready_to_submit": False,
        "readiness": "these files cannot be read as one experiment: " + issue,
        "found": {"readable": False, "assembled_from_loose_files": True},
        "fix_list": [{
            "priority": 0, "kind": "archive", "claim_id": None, "quantity": None,
            "source_location": None, "issue": issue, "fix": fix,
        }],
        "note": _ARCHIVE_NOTE,
    }


def render_archive_human(
    archive: str | os.PathLike[str] | bytes, *, claims: Sequence[Claim] = ()
) -> str:
    """A plain-text archive check an author can act on directly."""
    return _render_report(archive_report(archive, claims=claims))


def _render_report(report: dict[str, Any]) -> str:
    """The plain-text rendering of an archive-shaped report, whatever assembled it."""
    found = report["found"]
    lines = ["ARCHIVE REPRODUCIBILITY CHECK", ""]
    verdict = "READY TO SUBMIT" if report["ready_to_submit"] else "NOT YET READY"
    lines.append(verdict)
    lines.append(f"  {report['readiness']}")
    lines.append("")
    if found["readable"]:
        lines.append("WHAT THE ARCHIVE SHIPS")
        for artifact in found["files"]:
            lines.append(f"  - {artifact['filename']} ({artifact['detected_format']})")
        # Not `claims`: that name is this function's parameter, the author's own reported results.
        counts = found["claims"]
        lines.append(
            f"  claims: {counts['targetable']} targetable "
            f"({counts['figure_referenced']} figure-referenced, no values), "
            f"{counts['not_targetable']} not targetable"
        )
        lines.append(f"  runs a reproducer can adopt verbatim: {found['adoptable_recipes']}")
        clock = found.get("run_time_unit", UNSTATED_UNIT)
        if clock != UNSTATED_UNIT:
            # "0 to 30" is 30 of something, and the document does not say. Stated, never judged.
            lines.append(f"  the times in that run are in the unit your model states: {clock}")
        checked = found.get("manuscript_claims_checked", 0)
        # An empty fix list must not be read as "it runs what the paper reports" when nothing was
        # compared against the paper. The count is what separates a passed check from an absent one.
        # "none" covers both ways the comparison does not happen — no results supplied, and no
        # experiment to compare them against — without asserting which, since the line's job is to
        # stop an empty fix list reading as a check that passed.
        lines.append(
            f"  results from your paper checked against this experiment: {checked}"
            if checked
            else "  results from your paper checked against this experiment: none, so whether it "
            "runs what your paper reports was not checked"
        )
        lines.append("")
    lines.append("FIX BEFORE YOU SUBMIT (most impactful first)")
    if not report["fix_list"]:
        # An empty list means two different things, and the headline above says which: nothing
        # to fix, or nothing this check was in a position to ask. Printing the first under a NOT
        # YET READY verdict is a report contradicting itself on its face.
        lines.append(
            "  (nothing — a reproducer can read this archive and knows what to check)"
            if report["ready_to_submit"]
            else "  (nothing this check is in a position to ask of you — see below)"
        )
    for item in report["fix_list"]:
        where = f"{item['quantity']}: " if item["quantity"] else ""
        lines.append(f"  - {where}{item['issue']}")
        lines.append(f"      fix: {item['fix']}")
    unvalued = found.get("curves_without_values") or []
    if unvalued:
        lines.append("")
        lines.append("WHAT A REPRODUCER WOULD HAVE TO READ OFF YOUR FIGURES")
        lines.append(
            "  Not a fix list, and it does not hold up your submission: publishing results as "
            "figures is what papers do."
        )
        shown = ", ".join(item["claim_id"] for item in unvalued[:5])
        rest = f" and {len(unvalued) - 5} more" if len(unvalued) > 5 else ""
        lines.append(
            f"  - {len(unvalued)} curve(s) are plotted with no values behind them ({shown}{rest}), "
            "so nobody can check them without first digitizing your figure — a reading with its "
            "own uncertainty, judged in a band twice as wide as a number you print"
        )
        lines.append(
            "  - shipping those series as a data file your document names (a SED-ML "
            "dataDescription selecting one column per curve) removes that step, and what a "
            "reproducer checks is then your recorded values rather than a measurement of a "
            "picture of them"
        )
    packages = found.get("not_a_time_course") or []
    if packages:
        lines.append("")
        lines.append("WHAT THIS CHECK DID NOT JUDGE")
        for package in packages:
            lines.append(
                f"  - your model declares the SBML '{package['package']}' package, so it is "
                f"{package['means']}."
            )
        lines.append(
            "    Whether the experiment states your published results, and whether a reproducer "
            "can adopt it verbatim, are time-course questions; they were withheld rather than "
            "answered, and nothing above asks you to make this model into a time course."
        )
    gaps = found.get("extraction_gaps") or []
    if gaps:
        lines.append("")
        lines.append("WHAT REPROLITH'S OWN EXTRACTION WOULD NOT CARRY")
        lines.append(
            "  Not a fix list: some of these the archive omits, and some it states perfectly well "
            "and Reprolith cannot represent. Nothing here distinguishes the two."
        )
        for gap in gaps:
            lines.append(f"  - {gap['element']}: {gap['detail']}")
    lines.append("")
    lines.append("WHAT THIS CHECK IS")
    lines.append(f"  {report['note']}")
    return "\n".join(lines)


def render_pair_human(
    sedml: str,
    sbml: str,
    *,
    claims: Sequence[Claim] = (),
    data_files: Mapping[str, str] = MappingProxyType({}),
    model_filename: str | None = None,
) -> str:
    """The pair check as plain text, saying up front that the archive around it was generated."""
    report = pair_report(
        sedml, sbml, claims=claims, data_files=data_files, model_filename=model_filename
    )
    return "\n".join([
        "These two files were checked as the archive they describe, which was assembled here.",
        "A defect in your own manifest is therefore out of reach: there is not one yet.",
        "",
        _render_report(report),
    ])


__all__ = [
    "archive_report",
    "presubmission_report",
    "render_archive_human",
    "render_presubmission_human",
]
