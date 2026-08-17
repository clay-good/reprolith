"""A read-only MCP server over the query surface (spec: ``mcp-server``).

Reprolith's agent-facing surface: an MCP server exposing the same catalog, status, certificate,
and gap queries a human reads through the repository, so an agent can call Reprolith mid-workflow
as a deterministic reproducibility oracle. Every tool here is read-only and side-effect-free
(spec: "Read-only and effectful tools are separated"), and every verdict returned carries its
scope flag and qualifications because the tools delegate to :class:`~reprolith.query.ReprolithQuery`
— the server computes no verdict of its own, so it cannot diverge from the repository ("Parity
with the human surface").

MCP is JSON-RPC 2.0 over stdio, so this needs no third-party SDK: :func:`handle_request` is a pure
function from a request object to a response object (testable without any I/O), and
:func:`serve_stdio` is the newline-delimited stdio loop around it.
"""

from __future__ import annotations

import json
import math
import os
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from .catalog import AmbiguousMerge, Catalog, CatalogEntry, Identifiers, IllegalTransition
from .enums import LifecycleState, ModelClass
from .query import ReprolithQuery
from .run import advance_to_outcome, require_same_paper
from .supersession import CertificateLedger

PROTOCOL_VERSION = "2024-11-05"

_ONE_DIGEST = {
    "type": "object",
    "properties": {"digest": {"type": "string", "description": "the certificate's content digest"}},
    "required": ["digest"],
}
_IDENTIFIER = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "doi": {"type": "string"},
        "pubmed_id": {"type": "string"},
        "accession": {"type": "string"},
    },
}

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_catalog",
        "description": "Browse catalog entries as blind public views (no ground-truth label).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "status",
        "description": "A paper's lifecycle status and recorded history, by identifier.",
        "inputSchema": _IDENTIFIER,
    },
    {
        "name": "certificate",
        "description": "The full certificate for a digest: content, verdicts, scope, and gaps.",
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "verdict",
        "description": "The scope-qualified verdict for a digest (never a bare boolean).",
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "gaps",
        "description": "The structured 'what was missing' report for a digest.",
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "presubmission",
        "description": (
            "Author-facing pre-submission check for a digest: readiness, per-claim verdicts, and "
            "a prioritized 'fix before you submit' list. Runs on your own model before publishing."
        ),
        "inputSchema": _ONE_DIGEST,
    },
    {
        "name": "certificates_for",
        "description": "Digests of every certificate issued for a paper, newest first.",
        "inputSchema": _IDENTIFIER,
    },
    {
        "name": "backlog_health",
        "description": "Backlog depth by state, class, and difficulty, and the labelled mix.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "self_validation",
        "description": (
            "Reprolith's blind self-validation track record — per model class and overall, how "
            "its verdicts matched independently-established ground truth. The evidence a verdict "
            "rests on."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dossier",
        "description": "The ingested dossier for an entry accession — its extracted model structure.",
        "inputSchema": {
            "type": "object",
            "properties": {"accession": {"type": "string"}},
            "required": ["accession"],
        },
    },
    {
        "name": "bundle",
        "description": "The reconstruction bundle for an entry accession — model, recipe, assumptions.",
        "inputSchema": {
            "type": "object",
            "properties": {"accession": {"type": "string"}},
            "required": ["accession"],
        },
    },
    {
        "name": "lint",
        "description": (
            "Deterministic linter: run a supplied SBML model under the pinned engine and judge "
            "a species curve against a claim's reference points. Needs the engine extra."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sbml": {"type": "string", "description": "the SBML model to run"},
                "species": {"type": "string", "description": "the output species to read"},
                "reference": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "reference values at the same steps+1 sample points",
                },
                "duration": {"type": "number"},
                "steps": {"type": "integer"},
            },
            "required": ["sbml", "species", "reference", "duration", "steps"],
        },
    },
    {
        "name": "lint_steady_state",
        "description": (
            "Deterministic logical linter: check whether a reported steady state is a fixed point "
            "of a supplied Boolean network. Rules map each node to a Boolean expression over the "
            "others (e.g. 'A & !B'); pure and dependency-free — no engine extra needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rules": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "node id -> Boolean rule expression over the other nodes",
                },
                "reported": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                    "description": "the reported steady state: node id -> 0/1",
                },
            },
            "required": ["rules", "reported"],
        },
    },
    {
        "name": "lint_estimation",
        "description": (
            "Deterministic estimation linter: judge a re-derived parameter estimate against a "
            "paper's reported estimate by relative error, at the wider estimation-level tolerance. "
            "Pure — no engine extra."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reported": {"type": "number", "description": "the paper's reported estimate"},
                "recovered": {"type": "number", "description": "the estimate your re-fit recovered"},
            },
            "required": ["reported", "recovered"],
        },
    },
    {
        "name": "lint_distribution",
        "description": (
            "Deterministic population linter: judge a simulated percentile envelope against a "
            "reported one, governed by the worst-matched band. Each band is {percentile, curve}. "
            "Pure — no engine extra."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "reported": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "reported percentile bands: [{percentile, curve:[...]}]",
                },
                "predicted": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "simulated percentile bands at the same percentiles",
                },
            },
            "required": ["reported", "predicted"],
        },
    },
    {
        "name": "lint_diffusion",
        "description": (
            "Deterministic spatial linter: evolve a 1-D concentration profile under diffusion (and "
            "optional decay) and judge it against a reported profile by curve distance. Pure — no "
            "engine extra."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "initial": {"type": "array", "items": {"type": "number"}},
                "reference": {"type": "array", "items": {"type": "number"}},
                "diffusivity": {"type": "number"},
                "dx": {"type": "number"},
                "dt": {"type": "number"},
                "steps": {"type": "integer"},
                "decay": {"type": "number", "description": "optional first-order decay rate"},
            },
            "required": ["initial", "reference", "diffusivity", "dx", "dt", "steps"],
        },
    },
    {
        "name": "lint_stochastic",
        "description": (
            "Deterministic stochastic linter: ingest an SBML reaction network, run a pinned "
            "Gillespie SSA ensemble, and judge a species' mean count against a reported value. "
            "Needs the engine extra."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sbml": {"type": "string", "description": "the SBML reaction network to run"},
                "species": {"type": "integer", "description": "the species index to read"},
                "reported_mean": {"type": "number"},
                "duration": {"type": "number"},
                "trajectories": {"type": "integer"},
                "seed": {"type": "integer"},
            },
            "required": ["sbml", "species", "reported_mean", "duration", "trajectories", "seed"],
        },
    },
    {
        "name": "lint_objective",
        "description": (
            "Deterministic FBA linter: solve a supplied SBML-fbc model's objective and judge its "
            "optimum against a reported value, under an optional medium (exchange reaction -> max "
            "uptake). Needs the engine and fba extras."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sbml": {"type": "string", "description": "the SBML-fbc model to solve"},
                "reported": {"type": "number", "description": "the reported optimal objective value"},
                "medium": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                    "description": "optional exchange-reaction id -> maximum uptake",
                },
            },
            "required": ["sbml", "reported"],
        },
    },
]


# Effectful tools change state and are kept separate from the read-only set (spec: mcp-server,
# "Read-only and effectful tools are separated"). They are offered only when the server is run
# with a mutable catalog.
EFFECTFUL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "submit_paper",
        "description": (
            "EFFECTFUL: add a candidate paper to the catalog as a queued ode-pkpd entry. "
            "Submitting the same paper again resolves to the existing entry, never a duplicate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "doi": {"type": "string"},
                "pubmed_id": {"type": "string"},
                "accession": {"type": "string"},
                "model_class": {"type": "string", "description": "default 'ode-pkpd'"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "claim_work",
        "description": (
            "EFFECTFUL: claim the next best unit of work, leased to the requester so concurrent "
            "requesters do not collide. Returns the leased entry, or that there is no eligible work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "requester": {"type": "string"},
                "model_class": {"type": "string", "description": "optional filter"},
                "lease_seconds": {"type": "number", "description": "default 3600"},
            },
            "required": ["requester"],
        },
    },
    {
        "name": "release_work",
        "description": (
            "EFFECTFUL: release a claimed entry (by accession) back to the queue. Only the lease "
            "holder may release it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"accession": {"type": "string"}, "requester": {"type": "string"}},
            "required": ["accession", "requester"],
        },
    },
    {
        "name": "record_result",
        "description": (
            "EFFECTFUL: record that a claimed entry's reproduction is done, evidenced by a "
            "published certificate. The outcome state is read from that certificate's verdict, "
            "never asserted by the caller, and the certificate must be for this entry's paper. "
            "Walks the entry to certified / failed / blocked and drops the lease, so the unit is "
            "not handed out again."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "accession": {"type": "string"},
                "requester": {"type": "string"},
                "digest": {"type": "string", "description": "the certificate's content digest"},
                "at": {"type": "string", "description": "optional timestamp for the history"},
            },
            "required": ["accession", "requester", "digest"],
        },
    },
    {
        "name": "requeue_entry",
        "description": (
            "EFFECTFUL: return a blocked entry to the queue because its missing input is now "
            "available, recording who said so and why. Only a blocked entry can be requeued."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "accession": {"type": "string"},
                "requester": {"type": "string"},
                "reason": {"type": "string", "description": "what is now available"},
                "at": {"type": "string", "description": "optional timestamp for the history"},
            },
            "required": ["accession", "requester", "reason"],
        },
    },
]


def submit_paper(catalog: Catalog, arguments: dict[str, Any]) -> dict[str, Any]:
    """Add a paper to the catalog (de-duplicated) and report exactly what changed."""
    identifiers = Identifiers(
        title=arguments["title"],
        doi=arguments.get("doi"),
        pubmed_id=arguments.get("pubmed_id"),
        accession=arguments.get("accession"),
    )
    existing = catalog.find(identifiers)
    # An omitted class is unassigned, not ODE PK/PD: defaulting put every unclassified paper on
    # the ODE pathway and made it the answer to a claim_work(model_class="ode-pkpd") request.
    entry = catalog.add(identifiers, ModelClass(arguments.get("model_class") or "unassigned"))
    return {
        "created": existing is None,
        "resolved_to_existing": existing is not None,
        "entry": entry.blind().to_dict(),
    }


def claim_work(catalog: Catalog, arguments: dict[str, Any], *, at: float) -> dict[str, Any]:
    """Claim the next best work item at time ``at``, leased to the requester."""
    model_class = ModelClass(arguments["model_class"]) if arguments.get("model_class") else None
    entry = catalog.claim_next(
        arguments["requester"],
        at=at,
        seconds=_bounded_lease(arguments.get("lease_seconds", 3600.0)),
        model_class=model_class,
    )
    if entry is None:
        return {"claimed": False, "reason": "no eligible work"}
    return {
        "claimed": True,
        "entry": entry.blind().to_dict(),
        "lease_expires": entry.lease_expires,
        "priority": catalog.priority_signals(entry),  # why this entry was offered
    }


def release_work(catalog: Catalog, arguments: dict[str, Any]) -> dict[str, Any]:
    """Release a claimed entry back to the queue; only the lease holder may."""
    entry = catalog.find(Identifiers(title="", accession=arguments["accession"]))
    if entry is None:
        return {"released": False, "reason": "unknown entry"}
    if entry.leased_to != arguments["requester"]:
        return {"released": False, "reason": "not the lease holder"}
    entry.release_lease()
    return {"released": True}


def _held_by_another(entry: CatalogEntry, requester: str, *, at: float) -> bool:
    """Whether a live lease held by someone other than ``requester`` covers this entry.

    An expired lease is not a hold — the entry is back in the pool — so the check is on
    liveness, not on ``leased_to`` alone; otherwise a stale name left by an abandoned claim
    would block the true holder from ever recording the work.
    """
    if entry.leased_to is None or entry.leased_to == requester:
        return False
    return entry.lease_expires is not None and at < entry.lease_expires


def _history_stamp(arguments: dict[str, Any], *, at: float) -> str:
    """The timestamp to record on a transition: the caller's, or the server clock in UTC."""
    stated = arguments.get("at")
    if stated:
        return str(stated)
    return datetime.fromtimestamp(at, tz=timezone.utc).isoformat()


def record_result(
    catalog: Catalog,
    query: ReprolithQuery,
    arguments: dict[str, Any],
    *,
    at: float,
) -> dict[str, Any]:
    """Record a claimed entry's reproduction as done, evidenced by a published certificate.

    This is the step that closes the loop. Without it an agent could claim an entry, do the
    work, and publish a certificate while the entry sat in ``queued`` — so the same unit was
    handed out again at lease expiry, and the catalog could never say what had been finished.

    Two things are deliberately not the caller's to assert. The outcome state is derived from
    the named certificate's own verdict, so an agent cannot record a success its certificate
    does not support; and the certificate must be about this entry's paper (checked on DOI and
    PubMed ID, the stable identifiers), so one paper's result cannot be filed under another's
    accession. The reply is the blind entry view, like every other surface — recording work
    never reveals whether the entry carries a ground-truth label.
    """
    accession = arguments["accession"]
    requester = arguments["requester"]
    entry = catalog.find(Identifiers(title="", accession=accession))
    if entry is None:
        return {"recorded": False, "reason": "unknown entry"}
    if _held_by_another(entry, requester, at=at):
        return {"recorded": False, "reason": "not the lease holder"}
    if entry.state is not LifecycleState.QUEUED:
        # advance_to_outcome silently no-ops off ``queued``; at a surface that reads as success.
        return {"recorded": False, "reason": f"entry is already {entry.state.value}"}
    certificate = query.certificate_object(arguments["digest"])
    if certificate is None:
        return {"recorded": False, "reason": "unknown certificate"}
    require_same_paper(entry, certificate, accession)

    advance_to_outcome(
        entry,
        certificate.overall,
        at=_history_stamp(arguments, at=at),
        actor=requester,
        blocked_reason=(
            certificate.gap_report[0]
            if certificate.gap_report
            else "the certificate reports no evaluable claim"
        ),
        reason=f"result recorded from certificate {arguments['digest']}",
    )
    # The work is finished, so the lease has nothing left to coordinate.
    entry.release_lease()
    return {
        "recorded": True,
        "state": entry.state.value,
        "overall": certificate.overall.value,
        "certificate": arguments["digest"],
        "entry": entry.blind().to_dict(),
    }


def requeue_entry(catalog: Catalog, arguments: dict[str, Any], *, at: float) -> dict[str, Any]:
    """Return a blocked entry to the queue now that its missing input is available.

    The lifecycle has always permitted ``blocked -> queued``, but no surface performed it, so an
    entry blocked on a paywalled supplement stayed out of the backlog forever even once the
    supplement arrived. ``reason`` says what is now available and is recorded in the history;
    an illegal move (an entry that is not blocked) raises and is reported as a tool error.
    """
    entry = catalog.find(Identifiers(title="", accession=arguments["accession"]))
    if entry is None:
        return {"requeued": False, "reason": "unknown entry"}
    requester = arguments["requester"]
    if _held_by_another(entry, requester, at=at):
        return {"requeued": False, "reason": "not the lease holder"}
    entry.transition(
        LifecycleState.QUEUED,
        at=_history_stamp(arguments, at=at),
        actor=requester,
        reason=arguments["reason"],
    )
    entry.release_lease()
    return {"requeued": True, "state": entry.state.value, "entry": entry.blind().to_dict()}


# The lint_* tools run unbounded pure-Python loops (finite-difference steps, SSA trajectories) whose
# length is a caller-supplied count. The stdio server is a single-threaded request loop, so one
# oversized request would wedge it for every caller. The untrusted MCP boundary therefore caps the
# iteration counts and grid sizes that drive those loops; the in-process library API
# (``reprolith.linter``) stays unbounded for trusted callers. The ceilings are generous — far above
# any real inline sanity check — and exist only to turn a pathological request into a clean error.
_MAX_LINT_ITERATIONS = 1_000_000
_MAX_LINT_POINTS = 100_000
# Some loops cost the product of two bounded arguments — a grid of points advanced over a number of
# steps — so each argument passing its own ceiling is not enough: 100,000 points × 1,000,000 steps is
# hours of work. This bounds the product at roughly a minute of the pure-Python solver.
_MAX_LINT_WORK = 100_000_000
# A Boolean network's work is exponential in its node count, so the node count is the size the
# logical linter has to bound: checking a fixed point walks the rules once per node, but reaching
# the answer for a larger network means enumerating 2^n states (or a SAT solve the caller shapes).
# Fourteen nodes is worst-case seconds, well past any inline sanity check an agent runs mid-workflow.
_MAX_LINT_NODES = 14
# A simulated duration is a caller-supplied size like any other: an SSA's event count is the
# integral of its propensities over the duration, so a large one is unbounded work even with the
# trajectory count capped, and the stdio loop is single-threaded.
_MAX_LINT_DURATION = 1.0e6
# A lease is a coordination hint an agent holds while it works; a week is far past any run.
_MAX_LEASE_SECONDS = 7 * 24 * 3600.0


def _bounded_duration(value: Any, *, name: str = "duration") -> float:
    duration = float(value)
    if not math.isfinite(duration) or duration <= 0.0 or duration > _MAX_LINT_DURATION:
        raise ValueError(
            f"{name} must be a positive finite number of time units, at most "
            f"{_MAX_LINT_DURATION:g}; got {value!r}"
        )
    return duration


def _bounded_lease(value: Any) -> float:
    """A lease has to be a real span of time.

    A non-positive lease expires the instant it is granted, so the entry is immediately re-offered
    and two agents work the same paper — the collision the lease exists to prevent. An unbounded
    one lets a single client hold the whole queue effectively forever.
    """
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0.0 or seconds > _MAX_LEASE_SECONDS:
        raise ValueError(
            f"lease_seconds must be a positive finite number of seconds, at most "
            f"{_MAX_LEASE_SECONDS:g} (one week); got {value!r}"
        )
    return seconds


def _bounded_count(value: Any, *, name: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > ceiling:
        raise ValueError(f"{name} must be an integer in [0, {ceiling}]; got {value!r}")
    return int(value)


def _bounded_length(sequence: Any, *, name: str) -> Any:
    if hasattr(sequence, "__len__") and len(sequence) > _MAX_LINT_POINTS:
        raise ValueError(f"{name} exceeds the {_MAX_LINT_POINTS}-point limit for a lint request")
    return sequence


def _bounded_work(operations: int, *, name: str) -> None:
    """Bound a loop whose cost is the *product* of two separately bounded arguments.

    A grid and a step count that each pass their own ceiling can still multiply into hours of
    single-threaded work, which is the same wedge the individual caps exist to prevent.
    """
    if operations > _MAX_LINT_WORK:
        raise ValueError(
            f"{name} = {operations} exceeds the {_MAX_LINT_WORK}-operation limit for a lint "
            "request; run a job this size through the library API rather than the shared server"
        )


def dispatch_tool(query: ReprolithQuery, name: str, arguments: dict[str, Any]) -> Any:
    """Call the named read-only query tool with the given arguments."""
    if name == "list_catalog":
        return query.list_catalog()
    if name == "status":
        return query.status(**_identifier_kwargs(arguments))
    if name == "certificate":
        return query.certificate(arguments["digest"])
    if name == "verdict":
        return query.verdict(arguments["digest"])
    if name == "gaps":
        return query.gaps(arguments["digest"])
    if name == "presubmission":
        return query.presubmission(arguments["digest"])
    if name == "certificates_for":
        return query.certificates_for(**_identifier_kwargs(arguments))
    if name == "backlog_health":
        return query.backlog_health()
    if name == "self_validation":
        return query.self_validation()
    if name == "dossier":
        return query.dossier(arguments["accession"])
    if name == "bundle":
        return query.bundle(arguments["accession"])
    if name == "lint":
        from .linter import lint_curve

        result = lint_curve(
            arguments["sbml"],
            arguments["species"],
            reference=tuple(_bounded_length(arguments["reference"], name="reference")),
            duration=_bounded_duration(arguments["duration"]),
            steps=_bounded_count(arguments["steps"], name="steps", ceiling=_MAX_LINT_ITERATIONS),
        )
        return result.to_dict()
    if name == "lint_steady_state":
        from .linter import lint_steady_state

        rules = arguments["rules"]
        if hasattr(rules, "__len__") and len(rules) > _MAX_LINT_NODES:
            raise ValueError(
                f"the network has {len(rules)} nodes, above the {_MAX_LINT_NODES}-node limit for a "
                "lint request; analysing a larger network is exponential work, so run it through "
                "the library API rather than the shared server"
            )
        return lint_steady_state(rules, arguments["reported"]).to_dict()
    if name == "lint_estimation":
        from .linter import lint_estimation

        return lint_estimation(arguments["reported"], arguments["recovered"]).to_dict()
    if name == "lint_distribution":
        from .linter import lint_distribution

        for side in ("reported", "predicted"):
            for band in _bounded_length(arguments[side], name=side):
                _bounded_length(band.get("curve", ()), name=f"{side} band curve")
        return lint_distribution(arguments["reported"], arguments["predicted"]).to_dict()
    if name == "lint_diffusion":
        from .linter import lint_diffusion

        initial = _bounded_length(arguments["initial"], name="initial")
        steps = _bounded_count(arguments["steps"], name="steps", ceiling=_MAX_LINT_ITERATIONS)
        _bounded_work(len(initial) * steps, name="grid points × steps")
        return lint_diffusion(
            initial,
            _bounded_length(arguments["reference"], name="reference"),
            diffusivity=arguments["diffusivity"],
            dx=arguments["dx"], dt=arguments["dt"],
            steps=steps,
            decay=arguments.get("decay", 0.0),
        ).to_dict()
    if name == "lint_stochastic":
        from .linter import lint_stochastic

        trajectories = _bounded_count(
            arguments["trajectories"], name="trajectories", ceiling=_MAX_LINT_ITERATIONS
        )
        _bounded_work(trajectories * _MAX_LINT_ITERATIONS, name="trajectories × events")
        return lint_stochastic(
            arguments["sbml"], species=arguments["species"],
            reported_mean=arguments["reported_mean"],
            duration=_bounded_duration(arguments["duration"]),
            trajectories=trajectories,
            seed=arguments["seed"],
            max_events=_MAX_LINT_ITERATIONS,
        ).to_dict()
    if name == "lint_objective":
        from .linter import lint_objective

        return lint_objective(
            arguments["sbml"],
            reported=arguments["reported"],
            medium=arguments.get("medium"),
        ).to_dict()
    raise KeyError(f"unknown tool: {name}")


def _identifier_kwargs(arguments: dict[str, Any]) -> dict[str, Any]:
    return {k: arguments[k] for k in ("title", "doi", "pubmed_id", "accession") if k in arguments}


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(
    query: ReprolithQuery,
    request: dict[str, Any],
    *,
    catalog: Catalog | None = None,
    on_change: Callable[[], None] | None = None,
    now: Callable[[], float] | None = None,
) -> dict[str, Any] | None:
    """Handle one JSON-RPC request; return the response, or ``None`` for a notification.

    Implements ``initialize``, ``tools/list``, and ``tools/call`` (plus the
    ``notifications/initialized`` notification). When a mutable ``catalog`` is supplied the
    effectful tools are offered too; ``on_change`` is called after a mutation so the caller can
    persist it, and ``now`` supplies the wall-clock time leasing needs (injected so the library
    stays deterministic). Without a catalog the server is read-only and effectful calls are
    refused.
    """
    if not isinstance(request, dict):
        # A well-formed JSON value that isn't an object (a bare number, string, list, or null)
        # is still an invalid JSON-RPC request; refuse it rather than crash on ``.get``.
        return _error(None, -32600, "invalid request: expected a JSON object")

    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "reprolith", "version": _version()},
            },
        )
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        tools = TOOL_DEFINITIONS + (EFFECTFUL_TOOLS if catalog is not None else [])
        return _result(request_id, {"tools": tools})
    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        try:
            if name == "submit_paper":
                if catalog is None:
                    raise KeyError("submit_paper is not enabled on this read-only server")
                data = submit_paper(catalog, arguments)
                if on_change is not None:
                    on_change()
            elif name == "claim_work":
                if catalog is None:
                    raise KeyError("claim_work is not enabled on this read-only server")
                data = claim_work(catalog, arguments, at=(now() if now is not None else 0.0))
                if on_change is not None:
                    on_change()
            elif name == "release_work":
                if catalog is None:
                    raise KeyError("release_work is not enabled on this read-only server")
                data = release_work(catalog, arguments)
                if on_change is not None:
                    on_change()
            elif name == "record_result":
                if catalog is None:
                    raise KeyError("record_result is not enabled on this read-only server")
                data = record_result(
                    catalog, query, arguments, at=(now() if now is not None else 0.0)
                )
                if on_change is not None:
                    on_change()
            elif name == "requeue_entry":
                if catalog is None:
                    raise KeyError("requeue_entry is not enabled on this read-only server")
                data = requeue_entry(catalog, arguments, at=(now() if now is not None else 0.0))
                if on_change is not None:
                    on_change()
            else:
                data = dispatch_tool(query, name, arguments)
        except (
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            AmbiguousMerge,
            IllegalTransition,
        ) as exc:
            # Unknown tool / bad args, a length mismatch, the engine being absent or diverging
            # (EngineUnavailable and NonFiniteSimulation are RuntimeErrors), or an effectful call
            # refusing a catalog conflict (AmbiguousMerge/IllegalTransition) are all tool-level
            # errors: report them to the caller rather than crash the server.
            return _result(
                request_id,
                {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True},
            )
        return _result(
            request_id,
            {"content": [{"type": "text", "text": json.dumps(data, sort_keys=True)}]},
        )

    if request_id is None:
        return None  # an unknown notification
    return _error(request_id, -32601, f"method not found: {method}")


def serve_stdio(
    query: ReprolithQuery,
    *,
    reader: IO[str] | None = None,
    writer: IO[str] | None = None,
    catalog: Catalog | None = None,
    on_change: Callable[[], None] | None = None,
    now: Callable[[], float] | None = None,
) -> None:
    """Serve over newline-delimited JSON-RPC on stdio (effectful tools if ``catalog`` given)."""
    reader = reader or sys.stdin
    writer = writer or sys.stdout
    for line in reader:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            # One malformed line must not kill the loop for every later caller.
            writer.write(json.dumps(_error(None, -32700, f"parse error: {exc}")) + "\n")
            writer.flush()
            continue
        try:
            response = handle_request(
                query, request, catalog=catalog, on_change=on_change, now=now
            )
        except Exception as exc:  # noqa: BLE001 - a handler bug must not wedge the server
            request_id = request.get("id") if isinstance(request, dict) else None
            response = _error(request_id, -32603, f"internal error: {exc}")
        if response is not None:
            writer.write(json.dumps(response) + "\n")
            writer.flush()


def _version() -> str:
    from . import __version__

    return __version__


def load_certificates(ledger: CertificateLedger, directory: Path | str) -> int:
    """Load every stored certificate JSON in ``directory`` into ``ledger``; return the count.

    Each file is a certificate's ``content`` dict; reloading is dependency-free (no engine),
    so the server can serve real certificates produced earlier by the milestone run.
    """
    from .persistence import certificate_from_content

    path = Path(directory)
    loaded = 0
    if path.is_dir():
        for file in sorted(path.glob("*.json")):
            ledger.issue(certificate_from_content(json.loads(file.read_text(encoding="utf-8"))))
            loaded += 1
    return loaded


def load_dossiers(directory: Path | str) -> dict[str, Any]:
    """Load stored JSON files into a dict keyed by their filename stem (the accession).

    Shared by the dossier and bundle directories: both store one JSON per entry accession.
    """
    path = Path(directory)
    loaded: dict[str, Any] = {}
    if path.is_dir():
        for file in sorted(path.glob("*.json")):
            loaded[file.stem] = json.loads(file.read_text(encoding="utf-8"))
    return loaded


def repository_data_root() -> Path:
    """The repository's ``datasets`` directory — the committed state every surface reads.

    Resolved relative to the source tree, because the datasets are committed data rather than
    packaged resources: an installed copy of the library does not carry them. Callers that read the
    default state should go through :func:`default_data_dir`, which says so plainly when the
    directory is absent instead of failing later on a missing file.
    """
    return Path(__file__).resolve().parents[2] / "datasets"


def default_data_dir() -> Path:
    """The persisted repository state both surfaces read by default (the PK/PD milestone run).

    This is the mutable work-queue catalog (the labelled PK/PD blind set) plus its dossiers and
    bundles. Published certificates span all six classes — see :func:`milestone_certificate_dirs`.

    Raises ``FileNotFoundError`` naming the cause when the committed data is not reachable, which
    is what an installed copy of the package sees: the datasets live in the repository, not in the
    wheel, so a surface run outside a source checkout must be pointed at a checkout's
    ``datasets/milestone`` directory instead.
    """
    milestone = repository_data_root() / "milestone"
    if not milestone.is_dir():
        raise FileNotFoundError(
            f"no committed repository state at {milestone}. Reprolith's datasets are part of the "
            "repository, not of the installed package, so a surface running outside a source "
            "checkout has to be pointed at one: pass --data-dir <checkout>/datasets/milestone, or "
            "run from a clone of the repository"
        )
    return milestone


def milestone_certificate_dirs() -> dict[str, Path]:
    """Every class's committed milestone certificate directory, keyed by its model-class label.

    The single source of truth for "all published certificates", shared by the read surfaces
    (which load them into the ledger so every class's verdicts are queryable) and the registry
    builder (which renders them). Reading the whole set here is what lets an agent or a human
    fetch any of the six classes' certificates, not just the PK/PD one.
    """
    datasets = repository_data_root()
    return {
        "ode-pkpd": datasets / "milestone" / "certificates",
        "constraint-based": datasets / "constraint_based" / "milestone" / "certificates",
        "kinetic": datasets / "kinetic" / "milestone" / "certificates",
        "logical": datasets / "logical" / "milestone" / "certificates",
        "stochastic": datasets / "stochastic" / "milestone" / "certificates",
        "spatial": datasets / "spatial" / "milestone" / "certificates",
    }


def milestone_agreement_reports() -> dict[str, dict[str, Any]]:
    """Each class's committed blind self-validation report, keyed by its model-class label.

    Sits beside :func:`milestone_certificate_dirs` (one directory up from each certificates
    folder). This is the credibility evidence — how each class's blind verdicts matched
    independently-established ground truth — so exposing it through the read surface lets an
    agent check Reprolith's validated track record before trusting a verdict.
    """
    reports: dict[str, dict[str, Any]] = {}
    for label, certs_dir in milestone_certificate_dirs().items():
        report_file = certs_dir.parent / "agreement_report.json"
        if report_file.is_file():
            reports[label] = json.loads(report_file.read_text(encoding="utf-8"))
    return reports


def load_repository(data_dir: Path | str, *, aggregate: bool = False) -> tuple[ReprolithQuery, Catalog]:
    """Load the persisted catalog, certificates, dossiers, and bundles into a read surface.

    The single loader both surfaces share — the human CLI (:mod:`reprolith.cli`) and the MCP
    server's ``main`` — so the terminal view and the agent view are guaranteed to read identical
    state ("Parity with the human surface"). Returns the read-only query and the mutable catalog
    (the caller decides whether to expose the effectful tools that mutate it).

    With ``aggregate`` the read surface also carries the whole committed cross-class milestone
    evidence: the ledger is loaded from every class's certificate directory
    (:func:`milestone_certificate_dirs`) so all six classes' published verdicts are queryable, and
    the per-class blind self-validation reports (:func:`milestone_agreement_reports`) are attached
    so the validated track record is queryable too. The mutable catalog, dossiers, and bundles
    still come from ``data_dir`` alone (the catalog is the work queue and must not be polluted by
    the read-only cross-class aggregation).
    """
    from .seed import seed_catalog

    directory = Path(data_dir)
    catalog_file = directory / "catalog.json"
    if catalog_file.is_file():
        catalog = Catalog.from_dict(json.loads(catalog_file.read_text(encoding="utf-8")))  # the run's real progress
    else:
        catalog = Catalog()
        seed_catalog(catalog)
    ledger = CertificateLedger()
    load_certificates(ledger, directory / "certificates")
    agreement_reports: dict[str, dict[str, Any]] = {}
    if aggregate:
        # Idempotent by digest, so re-loading data_dir's own certificates here is harmless.
        for certs_dir in milestone_certificate_dirs().values():
            load_certificates(ledger, certs_dir)
        agreement_reports = milestone_agreement_reports()
    dossiers = load_dossiers(directory / "dossiers")
    bundles = load_dossiers(directory / "bundles")
    query = ReprolithQuery(catalog, ledger, dossiers, bundles, agreement_reports=agreement_reports)
    return query, catalog


def write_json_atomically(path: Path, payload: Any) -> None:
    """Write ``payload`` as JSON to ``path`` so a failed write cannot leave a half-written file.

    The catalog is rewritten in full on every mutation, and it is the file both surfaces read at
    startup — so a write interrupted by a signal, a crash, or a full disk truncates it and the next
    start of the server *and* the CLI dies on the unparseable remains. Writing to a sibling
    temporary file and renaming it into place makes the replacement atomic: the reader sees either
    the previous catalog or the new one, never a fragment.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)  # leave no debris beside the intact original
        raise


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover - stdio entry point
    """Run the server over stdio, loading the persisted catalog, certificates, and artifacts.

    ``--data-dir`` points the server at a repository state other than the committed milestone run —
    the same escape hatch the human CLI has, and the only way to run an installed copy of the
    package, which carries no datasets of its own.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="reprolith-mcp", description="Serve the Reprolith read surface over MCP on stdio."
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="repository state to read (default: the committed milestone run in a source checkout)",
    )
    args = parser.parse_args(argv)

    milestone = Path(args.data_dir) if args.data_dir is not None else default_data_dir()
    catalog_file = milestone / "catalog.json"
    query, catalog = load_repository(milestone, aggregate=True)

    def save() -> None:
        write_json_atomically(catalog_file, catalog.to_dict())

    import time

    serve_stdio(
        query,
        catalog=catalog,
        on_change=save,
        now=time.time,
    )


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "EFFECTFUL_TOOLS",
    "PROTOCOL_VERSION",
    "TOOL_DEFINITIONS",
    "claim_work",
    "default_data_dir",
    "dispatch_tool",
    "handle_request",
    "load_certificates",
    "load_dossiers",
    "load_repository",
    "milestone_agreement_reports",
    "milestone_certificate_dirs",
    "record_result",
    "release_work",
    "requeue_entry",
    "serve_stdio",
    "submit_paper",
]
