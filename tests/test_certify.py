"""Claim parsing from the claims dataset (pure; the engine-backed run is in test_worked_example)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from reprolith import Claim, ReferenceKind, load_claims_dataset
from reprolith.certify import _metric
from reprolith.engine import NonFiniteSimulation, require_finite

_CLAIMS = Path(__file__).parent.parent / "datasets" / "pkpd_claims.json"

# An estimation claim must state how its estimate was recovered: this glue does not run the re-fit,
# so the objective, optimizer, starting values, and dataset are the only evidence one happened.
_PROTOCOL = (
    "maximum likelihood, Nelder-Mead from the paper's Table 2 initial estimates, "
    "over the shipped plasma dataset"
)


def test_require_finite_passes_finite_and_rejects_inf_nan() -> None:
    # A diverging/too-stiff model yields inf/nan; require_finite signals that so the entry can
    # be recorded as blocked rather than pass garbage numbers downstream.
    assert require_finite((1.0, 2.0, 3.0), "A") == (1.0, 2.0, 3.0)
    with pytest.raises(NonFiniteSimulation):
        require_finite((1.0, float("inf")), "A")
    with pytest.raises(NonFiniteSimulation):
        require_finite((1.0, float("nan")), "A")


def test_load_claims_dataset_reads_the_shipped_dataset() -> None:
    data = load_claims_dataset(_CLAIMS)
    assert "BIOMD0000001028" in data["entries"]  # metformin, the one verified entry
    assert data["entries"]["BIOMD0000001028"]["claims"]


def test_metric_derives_cmax_auc_and_final() -> None:
    times = (0.0, 1.0, 2.0, 3.0)
    values = (0.0, 4.0, 2.0, 1.0)
    assert _metric(times, values, "cmax") == 4.0
    assert _metric(times, values, "final") == 1.0
    # trapezoidal area: (0+4)/2 + (4+2)/2 + (2+1)/2 = 2 + 3 + 1.5 = 6.5
    assert _metric(times, values, "auc") == pytest.approx(6.5)
    with pytest.raises(ValueError):
        _metric(times, values, "nonsense")


def test_claim_from_record_parses_overrides_and_flags() -> None:
    record = {
        "claim_id": "Cmax-1000mg", "quantity": "plasma Cmax", "species": "mPlasmaVenous",
        "reported": 11.2, "source_location": "Chung dataset", "metric": "cmax",
        "parameter_overrides": {"Metformin_Dose_in_Lumen_in_mg": 779.9},
        "assumption_qualified": True,
    }
    claim = Claim.from_record(record)
    assert claim.reported == 11.2
    assert claim.parameter_overrides == (("Metformin_Dose_in_Lumen_in_mg", 779.9),)
    assert claim.assumption_qualified
    assert claim.reference_kind is ReferenceKind.NUMERIC


def test_claim_from_record_defaults() -> None:
    claim = Claim.from_record({
        "claim_id": "c", "quantity": "AUC", "species": "C_p", "reported": 100.0,
        "source_location": "Table 2",
    })
    assert claim.metric == "cmax"  # default
    assert claim.parameter_overrides == ()
    assert not claim.assumption_qualified


def test_claims_dataset_records_parse() -> None:
    data = json.loads(_CLAIMS.read_text(encoding="utf-8"))
    for entry in data["entries"].values():
        assert entry["model_file"] and entry["paper"]["doi"]
        claims = [Claim.from_record(r) for r in entry["claims"]]
        assert claims and all(c.source_location for c in claims)  # every claim cites its source


def test_certify_estimation_records_a_distinct_estimation_verdict() -> None:
    from reprolith import (
        Attribution,
        EnginePin,
        EstimationClaim,
        FailureMode,
        Fault,
        OverallVerdict,
        PaperIdentity,
        ReproductionLevel,
        Verdict,
        certify_estimation,
    )

    cert = certify_estimation(
        paper=PaperIdentity(title="A data-shipping PK paper", doi="10.9/est"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        claims=[
            EstimationClaim(
                claim_id="cl", quantity="CL/F estimate", reported=3.20, recovered=3.30,
                source_location="Table 3",
                protocol=_PROTOCOL,
            ),
            EstimationClaim(
                claim_id="vc", quantity="Vc estimate", reported=10.0, recovered=18.0,
                source_location="Table 3",
                protocol=_PROTOCOL,
                shortfall=Attribution(
                    mode=FailureMode.LOCAL_OPTIMUM, implicated="central volume",
                    fault=Fault.RECONSTRUCTION,
                ),
            ),
        ],
    )
    assert all(a.level is ReproductionLevel.ESTIMATION for a in cert.assessments)
    verdicts = {a.claim_id: a.verdict for a in cert.assessments}
    assert verdicts["cl"] is Verdict.REPRODUCED  # ~3% inside the 10% estimation default
    assert verdicts["vc"] is Verdict.FAILED
    assert cert.overall is OverallVerdict.PARTIALLY_REPRODUCED
    assert all(a.protocol == _PROTOCOL for a in cert.assessments)


def test_a_time_course_certificate_records_the_run_behind_each_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A simulated metric is a function of its window, its sample count, and its dose.

    Without them the published number cannot be re-derived from the certificate, and a run over a
    vanishingly short duration returns the initial condition and reads as a clean reproduction.
    The simulator is stubbed (the engine extra is not in the dependency-free gate); what is under
    test is what the assessment records, not what the integrator returns.
    """
    import reprolith.certify as certify_module
    from reprolith import Claim, CurveClaim, EnginePin, PaperIdentity, certify_curves, certify_model

    times = tuple(float(i) for i in range(11))
    monkeypatch.setattr(
        certify_module, "simulate", lambda *a, **k: (times, tuple(5.0 for _ in times))
    )
    monkeypatch.setattr(certify_module, "_apply_overrides", lambda sbml, overrides: sbml)
    paper = PaperIdentity(title="A paper with a dose", doi="10.0/protocol")
    pin = EnginePin(engine="test-engine", version="0.0.0")

    scalar = certify_model(
        "<sbml/>", paper=paper, engine_pin=pin, duration=10.0, steps=10,
        claims=[Claim(claim_id="cmax", quantity="plasma Cmax", species="C", reported=5.0,
                      source_location="Table 1",
                      parameter_overrides=(("Dose_mg", 779.9),))],
    )
    assert scalar.assessments[0].protocol == (
        "duration=10.0, steps=10, read=[C] cmax, overrides: Dose_mg=779.9"
    )

    curve = certify_curves(
        "<sbml/>", paper=paper, engine_pin=pin,
        claims=[CurveClaim(claim_id="course", quantity="plasma concentration", species="C",
                           reference=tuple(5.0 for _ in times), source_location="Fig 1",
                           duration=10.0, steps=10)],
    )
    assert curve.assessments[0].protocol == "duration=10.0, steps=10, read=[C] curve"
    # It travels into the published content, so a reader holding the file can re-run it.
    assert curve.content()["assessments"][0]["protocol"] == "duration=10.0, steps=10, read=[C] curve"


def test_an_estimation_claim_that_states_no_protocol_is_refused() -> None:
    """A re-fit nobody can repeat is not evidence, and `recovered == reported` proves nothing."""
    from reprolith import EstimationClaim

    with pytest.raises(ValueError, match="states no protocol"):
        EstimationClaim(
            claim_id="cl", quantity="CL/F estimate", reported=3.2, recovered=3.2,
            source_location="Table 3", protocol="",
        )


def test_an_override_the_run_would_ignore_is_refused_rather_than_published() -> None:
    """A parameter a rule determines is recomputed by the solver, so setting it changes nothing.

    The protocol would then name an override the run never had — the certificate asserting a
    condition it did not hold. The shipped metformin model has such parameters (its assignment-rule
    blood flows); moving one by fifteen orders of magnitude left the Cmax untouched.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.certify import _apply_overrides

    rule_model = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="ruled">
    <listOfParameters>
      <parameter id="k" value="1" constant="true"/>
      <parameter id="derived" value="2" constant="false"/>
    </listOfParameters>
    <listOfRules>
      <assignmentRule variable="derived">
        <math xmlns="http://www.w3.org/1998/Math/MathML"><ci> k </ci></math>
      </assignmentRule>
    </listOfRules>
  </model>
</sbml>"""
    with pytest.raises(ValueError, match="determined by a rule"):
        _apply_overrides(rule_model, (("derived", 5.0),))
    # A parameter nothing determines is still overridable, and an unknown one still refused.
    assert "5" in _apply_overrides(rule_model, (("k", 5.0),))
    with pytest.raises(ValueError, match="not in the model"):
        _apply_overrides(rule_model, (("absent", 5.0),))


def test_the_protocol_prints_the_value_that_was_run_and_what_was_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Six significant figures printed two distinct doses identically, and named no readout.

    A dose rounded for display is a number a reader re-running the claim does not get, and two
    claims that differ only by peak-versus-area were indistinguishable on the certificate.
    """
    import reprolith.certify as certify_module
    from reprolith import Claim, EnginePin, PaperIdentity, certify_model

    times = tuple(float(i) for i in range(3))
    monkeypatch.setattr(certify_module, "simulate", lambda *a, **k: (times, (1.0, 1.0, 1.0)))
    monkeypatch.setattr(certify_module, "_apply_overrides", lambda sbml, overrides: sbml)
    cert = certify_model(
        "<sbml/>", paper=PaperIdentity(title="p", doi="10.0/x"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"), duration=2.0, steps=2,
        claims=[Claim(claim_id="c", quantity="q", species="C", reported=1.0,
                      source_location="Table 1",
                      parameter_overrides=(("dose", 389.9200009),))],
    )
    assert "dose=389.9200009" in cert.assessments[0].protocol
    assert "read=[C] cmax" in cert.assessments[0].protocol


def test_an_override_an_event_may_overwrite_is_allowed() -> None:
    """Deliberate, and reversed from an earlier round that refused it.

    An event assignment looked like the same not-taking override as a rule or an initial
    assignment, and it is not: an event overwrites its target only when its trigger fires, so an
    override still governs the run up to that moment and governs all of it when the trigger is
    never satisfied in the protocol window. Refusing it rejected three measured shapes whose
    overrides each moved the answer threefold. The residual gap — a certificate reporting an
    override without saying an event may overwrite it — needs the trigger evaluated over the
    window, and is recorded in docs/findings-note.md rather than guessed at with a name lookup.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.certify import _apply_overrides

    event_model = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="dosed">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfParameters>
      <parameter id="kin" value="0" constant="false"/>
    </listOfParameters>
    <listOfEvents>
      <event id="dose" useValuesFromTriggerTime="true">
        <trigger initialValue="false" persistent="true">
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><gt/><csymbol encoding="text"
              definitionURL="http://www.sbml.org/sbml/symbols/time"> t </csymbol>
              <cn> 100 </cn></apply>
          </math>
        </trigger>
        <listOfEventAssignments>
          <eventAssignment variable="kin">
            <math xmlns="http://www.w3.org/1998/Math/MathML"><cn> 1 </cn></math>
          </eventAssignment>
        </listOfEventAssignments>
      </event>
    </listOfEvents>
  </model>
</sbml>"""
    assert "3" in _apply_overrides(event_model, (("kin", 3.0),))


def test_an_override_a_local_parameter_shadows_is_refused() -> None:
    """A kinetic law's own local parameter shadows a global of the same id, and the law reads it.

    So the override is accepted, the run comes back bit-identical, and the protocol publishes an
    override the run never had — the third route by which an override fails to take. An *event*
    assignment is deliberately not refused: it overwrites its target only when its trigger fires,
    so an override still governs the run up to that moment and may govern all of it.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.certify import _apply_overrides

    shadowed = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="shadowed">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="A" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="k" value="1" constant="true"/>
      <parameter id="free" value="1" constant="true"/>
    </listOfParameters>
    <listOfReactions>
      <reaction id="decay" reversible="false">
        <listOfReactants><speciesReference species="A" stoichiometry="1" constant="true"/></listOfReactants>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><times/><ci> k </ci><ci> A </ci></apply>
          </math>
          <listOfLocalParameters><localParameter id="k" value="0.5"/></listOfLocalParameters>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>"""
    with pytest.raises(ValueError, match="shadowed by a kinetic law"):
        _apply_overrides(shadowed, (("k", 3.0),))
    # A global nothing shadows is still overridable.
    assert "5" in _apply_overrides(shadowed, (("free", 5.0),))


def test_a_global_a_rule_reads_is_not_treated_as_shadowed() -> None:
    """The shadow guard counted kinetic laws only, and everything else reads the global.

    One reaction declaring a local `k` made a global `k` that a rate rule integrates look fully
    shadowed, so an override of it was refused under a message saying it has no effect on the run.
    Measured: it moved the answer 54.6x. Same shape as the case the previous round fixed, one
    route over — a rule, an initial assignment or an event reads global scope and cannot be
    shadowed by any reaction's local.
    """
    pytest.importorskip(
        "libsbml", reason="the optional 'engine' extra (python-libsbml) is not installed"
    )
    from reprolith.certify import _apply_overrides

    rule_reads_global = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4"><model id="m">
 <listOfCompartments><compartment id="c" size="1"/></listOfCompartments>
 <listOfSpecies>
  <species id="A" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"/>
  <species id="D" compartment="c" initialAmount="1" hasOnlySubstanceUnits="true"/>
 </listOfSpecies>
 <listOfParameters><parameter id="k" value="0.1"/></listOfParameters>
 <listOfRules><rateRule variable="D">
  <math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k</ci><ci>D</ci></apply></math>
 </rateRule></listOfRules>
 <listOfReactions><reaction id="R1" reversible="false">
  <listOfReactants><speciesReference species="A"/></listOfReactants>
  <kineticLaw><math xmlns="http://www.w3.org/1998/Math/MathML"><apply><times/><ci>k</ci><ci>A</ci></apply></math>
   <listOfParameters><parameter id="k" value="5.0"/></listOfParameters></kineticLaw>
 </reaction></listOfReactions></model></sbml>"""

    # It governs the rate rule, so overriding it takes — and must not be refused.
    assert "0.9" in _apply_overrides(rule_reads_global, (("k", 0.9),))


def test_a_curve_claim_with_no_reference_abstains_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shape of a claim read off a shipped SED-ML: which curve is plotted, not its values.

    Judging a run against an empty reference used to raise, so the one front-end most likely to
    meet a reference-less claim crashed on it instead of abstaining.
    """
    import reprolith.certify as certify_module
    from reprolith import (
        CurveClaim,
        EnginePin,
        OverallVerdict,
        PaperIdentity,
        Verdict,
        certify_curves,
        claim_counts,
    )

    times = tuple(float(i) for i in range(11))
    ran: list[str] = []

    def _record(sbml: str, species: str, **kwargs: object) -> tuple[tuple[float, ...], ...]:
        ran.append(species)
        return times, tuple(5.0 for _ in times)

    monkeypatch.setattr(certify_module, "simulate", _record)
    certificate = certify_curves(
        "<sbml/>",
        paper=PaperIdentity(title="A document with two figures", doi="10.0/sedml"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        claims=[
            CurveClaim(claim_id="fig2a", quantity="MAPK_PP", species="MAPK_PP", reference=(),
                       source_location="SED-ML plot2D 'plot_0' (Figure 2A)",
                       duration=9000.0, steps=10),
            CurveClaim(claim_id="checked", quantity="MAPK", species="MAPK",
                       reference=tuple(5.0 for _ in times), source_location="Fig 1",
                       duration=10.0, steps=10),
        ],
    )

    abstained, judged = certificate.assessments
    assert abstained.verdict is Verdict.NOT_EVALUABLE
    assert "nothing to compare" in (abstained.root_cause or "")
    assert judged.verdict is Verdict.REPRODUCED
    # The claim it cannot check is not run at all.
    assert ran == ["MAPK"]
    # The documented overall rule counts only evaluable claims, so this is a `reproduced` whose
    # own claim counts show one claim nobody could check — the abstention is visible, not folded
    # into the pass.
    assert certificate.overall is OverallVerdict.REPRODUCED
    assert claim_counts(certificate)["not-evaluable"] == 1
