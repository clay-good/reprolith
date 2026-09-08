#!/usr/bin/env python3
"""Re-render the certificate texts that ship outside a milestone directory.

Three published renders live in worked-example directories rather than under a class's
`milestone/certificates/`: the metformin PK/PD certificate the README and `docs/mcp-server.md`
send readers to, the E. coli core constraint-based one, and the logical toggle switch. Nothing
regenerated them, so they drifted: the metformin text was still naming an engine pin with no judge
revision, and a protocol line produced by code that no longer exists. `tests/test_pins.py` now
gates every committed render against the current revision, and this is the script that satisfies
it. Run from the repo root, after the milestone scripts:

    python scripts/render_worked_examples.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any

from reprolith import (
    Certificate,
    EstimationClaim,
    PaperIdentity,
    PercentileBand,
    PopulationClaim,
    RunMetadata,
    SubjectVariability,
    certificate_from_content,
    certify_estimation,
    certify_logical,
    certify_population,
    engine_pin,
    refit_parameters,
    render_human,
    simulate_population,
)
from reprolith.constraint_based import certify_constraint_based
from reprolith.fba import solver_pin as fba_pin
from reprolith.logical import LogicalClaim
from reprolith.logical import solver_pin as logical_pin
from reprolith.persistence import dossier_from_dict

ROOT = Path(__file__).parent.parent
#: One fixed stamp for every render this script writes; run metadata is outside the content hash
#: and `render_human` prints none of it, so this keeps each render reproducible byte for byte.
_RUN = RunMetadata(created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1")
DATASETS = ROOT / "datasets"

# Each render, and the committed certificate it is the rendering *of*. Re-rendering from the
# machine-readable certificate is what keeps the two accounts of one result from disagreeing —
# which is exactly how the metformin text came to publish a weaker pin than its own JSON.
FROM_JSON = [
    (
        DATASETS / "milestone" / "certificates" / "BIOMD0000001028.json",
        DATASETS / "worked_examples" / "metformin_reproduction_certificate.txt",
    ),
]

_CB = DATASETS / "constraint_based"


def _e_coli_certificate() -> Certificate:
    """Re-certified from the worked example's own dossier, not from the milestone certificate.

    The milestone run certifies the same model from the same dossier but under a PaperIdentity
    carrying no doi, so rendering the worked example from that JSON would silently drop the
    citation the worked example exists to teach.
    """
    dossier = dossier_from_dict(
        json.loads((_CB / "worked_example" / "dossier.json").read_text(encoding="utf-8"))
    )
    cert = certify_constraint_based(
        dossier,
        sbml=(_CB / "e_coli_core.xml").read_text(encoding="utf-8"),
        paper=PaperIdentity(
            title="E. coli core metabolic model (Orth, Fleming & Palsson 2010)",
            doi="10.1128/ecosalplus.10.2.1",
        ),
        engine_pin=fba_pin(),
    )
    return cert


# The toggle switch has no milestone certificate — it is built from its two claims, and
# `tests/test_logical_worked_example.py` regenerates it byte for byte, so the recipe lives in both
# places and must stay identical.
_TOGGLE_RULES = {"A": "!B", "B": "!A"}


def _toggle_certificate() -> Certificate:
    cert = certify_logical(
        paper=PaperIdentity(
            title="Toggle switch — a two-gene mutual-repression circuit", doi="10.0/toggle"
        ),
        engine_pin=logical_pin(),
        claims=[
            LogicalClaim(claim_id="ss_on", quantity="A-ON steady state", rules=_TOGGLE_RULES,
                         reported={"A": 1, "B": 0}, source_location="Fig 1a"),
            LogicalClaim(claim_id="ss_off", quantity="A-OFF steady state", rules=_TOGGLE_RULES,
                         reported={"A": 0, "B": 1}, source_location="Fig 1b"),
        ],
    )
    return cert


#: The one-compartment IV-bolus model both deferred halves are demonstrated on: a dose `D` into a
#: volume `V`, eliminated first-order at `k`. It is the model whose population percentiles and
#: whose re-fit both have closed forms, which is what lets these two renders be checked against
#: mathematics rather than against themselves.
_ONE_COMPARTMENT = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="one_compartment">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="C" compartment="c" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="D" value="100" constant="true"/>
      <parameter id="V" value="10" constant="true"/>
      <parameter id="k" value="0.2" constant="true"/>
    </listOfParameters>
    <listOfInitialAssignments>
      <initialAssignment symbol="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><divide/><ci>D</ci><ci>V</ci></apply>
        </math>
      </initialAssignment>
    </listOfInitialAssignments>
    <listOfRules>
      <rateRule variable="C">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><minus/><apply><times/><ci>k</ci><ci>C</ci></apply></apply>
        </math>
      </rateRule>
    </listOfRules>
  </model>
</sbml>
"""
_DOSE, _VOLUME, _RATE = 100.0, 10.0, 0.2
_POPULATION_CV = 0.3
_SUBJECTS = 500
_POPULATION_SEED = 20260901
_PERCENTILES = (5.0, 50.0, 95.0)
_DURATION, _STEPS = 12.0, 12


def _closed_form_band(percentile: float, omega: float, time: float) -> float:
    """The exact percentile of C(t) when V is log-normal: the median times exp(omega·z_p).

    This is the *paper* in these two renders. Neither deferred half has ever been pointed at a
    published population figure or a published dataset — there is none in this corpus — so what
    stands in for one is mathematics that is right independently of anything Reprolith computes.
    """
    return (
        (_DOSE / _VOLUME)
        * math.exp(-_RATE * time)
        * math.exp(omega * NormalDist().inv_cdf(percentile / 100.0))
    )


def _population_certificate() -> tuple[Certificate, dict[str, Any]]:
    """Model -> ensemble -> envelope -> certificate, with nothing typed by hand between them.

    The population half shipped its oracle first and its simulator later, and for a while the two
    met only in a docstring. They meet in a test now — and in *this* render, which is the first
    published artifact either half produced: `docs/population-and-estimation.md` could say the
    capability was validated and had to add that no reader could see a certificate from it.

    The verdict comes back `partially-reproduced` on a claim that reproduces cleanly, which is the
    class's honesty invariant rather than a shortfall: a population verdict rests on a reconstructed
    variability model and a sampling choice, and the certificate says so as an assumption.
    """
    spec = SubjectVariability(parameter="V", cv=_POPULATION_CV)
    run = simulate_population(
        _ONE_COMPARTMENT, "C", duration=_DURATION, steps=_STEPS,
        variability=(spec,), subjects=_SUBJECTS, seed=_POPULATION_SEED,
    )
    reported = tuple(
        PercentileBand(
            percentile=percentile,
            curve=tuple(_closed_form_band(percentile, spec.omega(), t) for t in run.times),
        )
        for percentile in _PERCENTILES
    )
    certificate = certify_population(
        paper=PaperIdentity(
            title=(
                "One-compartment IV bolus with log-normal volume — the population envelope its "
                "own mathematics predicts"
            ),
            doi="",
        ),
        engine_pin=engine_pin(),
        claims=[PopulationClaim(
            claim_id="population-envelope",
            quantity="5th/50th/95th percentile of C(t) across the population",
            reported=reported,
            predicted=run.bands,
            source_location=(
                "closed form: C(t) = (D/V)·exp(-k·t)·exp(omega·z_p) for a log-normal V — "
                "mathematics standing in for a published figure, not a number read from a paper"
            ),
            protocol=run.protocol,
        )],
    )
    reference = {
        "description": (
            "The envelope a paper would print if its population were exactly the one modelled: "
            "the closed-form percentiles of C(t) for a log-normal volume, which is what the "
            "committed certificate is judged against."
        ),
        "model": "one-compartment IV bolus, D=100, V=10 (log-normal, CV 0.3), k=0.2",
        "times": list(run.times),
        "bands": {str(band.percentile): list(band.curve) for band in reported},
    }
    return certificate, reference


def _estimation_certificate() -> tuple[Certificate, dict[str, Any]]:
    """Data -> re-fit -> certificate, the same walk for the other deferred half.

    The observations are the model's own trajectory at the parameters below, so the estimate has a
    right answer that is not Reprolith's: a fit that recovers `k` has recovered the number the data
    was generated from. Like the population render, mathematics standing in for a paper, because
    no shipped dataset in this corpus is a paper's raw data.
    """
    observations = tuple(
        (time, (_DOSE / _VOLUME) * math.exp(-_RATE * time))
        for time in (0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
    )
    result = refit_parameters(
        _ONE_COMPARTMENT, "C",
        observations=observations,
        start=(("k", 0.05),),
        dataset="the model's own trajectory at k=0.2, standing in for a paper's raw data",
    )
    certificate = certify_estimation(
        paper=PaperIdentity(
            title="One-compartment IV bolus — the elimination rate re-fitted from its own data",
            doi="",
        ),
        engine_pin=engine_pin(),
        claims=[EstimationClaim(
            claim_id="elimination-rate",
            quantity="elimination rate constant k (1/h)",
            reported=_RATE,
            recovered=result.value("k"),
            source_location=(
                "the value the observations were generated from — mathematics standing in for a "
                "paper's reported estimate, not a number read from one"
            ),
            protocol=result.protocol,
        )],
    )
    reference = {
        "description": (
            "The observations the fit was run against and the parameter they were generated "
            "from, so the recovered estimate has a right answer that is not Reprolith's."
        ),
        "model": "one-compartment IV bolus, D=100, V=10, k=0.2",
        "true_k": _RATE,
        "start_k": 0.05,
        "observations": [list(pair) for pair in observations],
    }
    return certificate, reference


def main() -> None:
    for source, target in FROM_JSON:
        content = json.loads(source.read_text(encoding="utf-8"))
        cert = certificate_from_content(content)
        # The committed certificate stores content only — run metadata is deliberately outside the
        # deterministic hash — and render_human prints none of it, so a fixed stamp keeps this
        # render reproducible byte for byte.
        run = RunMetadata(
            created_at="2026-08-07T00:00:00Z", actor="worked-example", tool_version="0.0.1"
        )
        target.write_text(render_human(cert, run) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(ROOT)} from {source.relative_to(ROOT)}")

    # Each of these two is rendered from a certificate this script builds rather than from one a
    # milestone published — the E. coli worked example re-certifies under a PaperIdentity carrying
    # the doi the milestone entry drops, and the toggle switch is built from its two claims. The
    # certificate is written out beside the render so the freshness gate can compare them byte for
    # byte, instead of having no sibling and being skipped, which is how a hand-edited verdict in a
    # committed render went unnoticed.
    population, population_reference = _population_certificate()
    estimation, estimation_reference = _estimation_certificate()
    for reference, directory in (
        (population_reference, DATASETS / "population" / "worked_example"),
        (estimation_reference, DATASETS / "estimation" / "worked_example"),
    ):
        # The "paper" each of these is judged against, committed beside the certificate: without it
        # a reader has the verdict and no way to see what it was a verdict about, and the check that
        # the numbers still line up would have to restate the mathematics a second time.
        (directory / "reference.json").write_text(
            json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    for certificate, directory in (
        (_e_coli_certificate(), _CB / "worked_example"),
        (_toggle_certificate(), DATASETS / "logical" / "worked_example"),
        (population, DATASETS / "population" / "worked_example"),
        (estimation, DATASETS / "estimation" / "worked_example"),
    ):
        (directory / "certificate.txt").write_text(
            render_human(certificate, _RUN) + "\n", encoding="utf-8"
        )
        (directory / "certificate.json").write_text(
            json.dumps(certificate.content(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {(directory / 'certificate.txt').relative_to(ROOT)} and its certificate.json")


if __name__ == "__main__":
    main()
