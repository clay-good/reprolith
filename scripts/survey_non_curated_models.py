#!/usr/bin/env python3
"""Measure the other half of the corpus's ceiling: how many unreached entries have a model that runs.

The table survey answered "whose paper states a result this can read" and found three papers in
ten. What it could not answer is the condition on the *other* side of a certificate: does the
entry's model run at all? The roadmap has carried "entries whose models run" as a lift ever since,
with no number attached to it. This attaches one.

Every non-curated SBML entry in the seeded set is fetched and probed: it is loaded, its rate laws
are counted, and the pinned engine is asked to complete a uniform time course over one of its state
variables at a ladder of durations. Dev-only and network-bound, like the other `survey_*` and
`regenerate_*` scripts; it needs the ``engine`` extra. It writes
``datasets/non_curated_survey.json``, which is what the test reads.

    python scripts/survey_non_curated_models.py

Three limits travel in the output rather than being left for a reader to discover:

* **A probe course is not the model's own run.** Nothing here knows the time scale a paper used, so
  a ladder of durations is tried and the longest one that completes is recorded. "Completes" is a
  floor for "runnable" and "completes none of them" is a floor for "not runnable" — neither is a
  verdict, and no claim is being reproduced.
* **A state variable is a species or a rate-rule target.** Several of these models keep their whole
  state in parameters driven by rate rules and declare no species at all; probing only species
  would have called them un-runnable for a reason that is about the probe.
* **Only the first few state variables are tried.** A model whose first variables fail is recorded
  as not completing, and how many were tried is written down beside the result.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "python"))

from reprolith import (  # noqa: E402
    packages_no_time_course_describes,
    reactions_without_rate_laws,
    simulate,
)
from reprolith.sbml import _libsbml  # noqa: E402

_METADATA = "https://www.ebi.ac.uk/biomodels/{accession}?format=json"
_DOWNLOAD = "https://www.ebi.ac.uk/biomodels/model/download/{accession}?filename={filename}"

#: The ladder of probe durations, shortest first. A model that completes the longest is not
#: thereby correct; a model that completes none of them cannot be run by asking it to.
_DURATIONS = (0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)

#: How many of a model's state variables to probe before recording that it does not complete.
_STATE_VARIABLES_TRIED = 3


def _fetch(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return bytes(response.read())


def _model_text(accession: str) -> str:
    meta = json.loads(_fetch(_METADATA.format(accession=accession), timeout=60).decode())
    filename = meta["files"]["main"][0]["name"]
    url = _DOWNLOAD.format(accession=accession, filename=urllib.parse.quote(filename))
    return _fetch(url).decode("utf-8", "replace")


def _state_variables(model: Any) -> list[str]:
    """Species that are not boundary conditions, then whatever rate rules drive.

    The second half is not a fallback. MODEL1006230040 declares no species at all and keeps its
    entire state in parameters under rate rules; the pinned engine reads those by id like any other
    output, and probing species alone would have reported it as un-runnable.
    """
    libsbml = _libsbml()
    state = [s.getId() for s in model.getListOfSpecies() if not s.getBoundaryCondition()]
    state += [
        rule.getVariable()
        for rule in model.getListOfRules()
        if rule.getTypeCode() == libsbml.SBML_RATE_RULE
    ]
    return state


def _probe(text: str, state: list[str]) -> dict[str, Any]:
    """The longest duration the pinned engine completes over any of the first few state variables."""
    longest: float | None = None
    through: str | None = None
    stopped = ""
    for name in state[:_STATE_VARIABLES_TRIED]:
        for duration in _DURATIONS:
            try:
                simulate(text, species=name, duration=duration, steps=10)
            except Exception as refused:  # noqa: BLE001 - every refusal is a result here
                stopped = f"{type(refused).__name__}: {refused}"
                break
            longest, through = duration, name
        if longest is not None:
            break
    return {
        "completes_a_course": longest is not None,
        "longest_duration_completed": longest,
        "probed_through": through,
        "state_variables_tried": min(len(state), _STATE_VARIABLES_TRIED),
        "stopped_with": stopped,
    }


def survey(accessions: list[str]) -> dict[str, Any]:
    libsbml = _libsbml()
    entries = []
    for accession in sorted(accessions):
        record: dict[str, Any] = {"accession": accession}
        text = _model_text(accession)
        model = libsbml.readSBMLFromString(text).getModel()
        if model is None:
            record["loads"] = False
            entries.append(record)
            continue
        state = _state_variables(model)
        record.update({
            "loads": True,
            "reactions": model.getNumReactions(),
            "reactions_without_rate_laws": len(reactions_without_rate_laws(text)),
            "rules": model.getNumRules(),
            "species": model.getNumSpecies(),
            "state_variables": len(state),
            "packages_no_time_course_describes": list(packages_no_time_course_describes(text)),
        })
        record.update(_probe(text, state))
        entries.append(record)
    runs = [e for e in entries if e.get("completes_a_course")]
    return {
        "description": (
            "Every non-curated SBML entry in the seeded set, probed for whether its model runs. "
            "The companion to datasets/manuscripts/table_survey.json, which asks whether the "
            "entry's paper states a result that can be read. A certificate needs both."
        ),
        "entries": entries,
        "models_that_complete_a_course": len(runs),
        "limits": [
            "A probe course is not the model's own run: nothing here knows the time scale the "
            "paper used, so a ladder of durations is tried and the longest that completes is "
            "recorded. Completing one is a floor for 'runnable' and completing none is a floor "
            "for 'not runnable'. No claim is reproduced and no verdict is reached.",
            "A state variable is a species that is not a boundary condition, or a rate rule's "
            "target. Several of these models declare no species at all and keep their whole state "
            "in parameters; probing species alone would have called them un-runnable for a reason "
            f"about the probe. Only the first {_STATE_VARIABLES_TRIED} are tried.",
            "Running is half of what a certificate needs. Whether the entry's paper states a "
            "result that can be read is the other half, and it is measured separately.",
        ],
    }


def main() -> int:
    survey_path = REPO / "datasets" / "manuscripts" / "table_survey.json"
    table_survey = json.loads(survey_path.read_text())
    accessions = [
        entry["accession"]
        for entry in table_survey["entries"]
        if entry["curation"] != "CURATED" and entry["model_format"] == "SBML"
    ]
    result = survey(accessions)
    out = REPO / "datasets" / "non_curated_survey.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        f"{result['models_that_complete_a_course']} of {len(accessions)} non-curated SBML models "
        f"complete a probe course -> {out.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
