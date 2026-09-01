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


_EVENT_MODEL = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">
  <model id="dosed">
    <listOfCompartments><compartment id="c" size="1" constant="true"/></listOfCompartments>
    <listOfSpecies>
      <species id="X" compartment="c" initialAmount="0" hasOnlySubstanceUnits="true"
               boundaryCondition="false" constant="false"/>
    </listOfSpecies>
    <listOfParameters>
      <parameter id="dose" value="100" constant="false"/>
      <parameter id="k" value="0.1" constant="true"/>
    </listOfParameters>
    <listOfRules>
      <rateRule variable="X">
        <math xmlns="http://www.w3.org/1998/Math/MathML">
          <apply><times/><ci>k</ci><ci>dose</ci></apply>
        </math>
      </rateRule>
    </listOfRules>
    <listOfEvents>
      <event id="reset_at_12h" useValuesFromTriggerTime="false">
        <trigger initialValue="false" persistent="true">
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply><gt/><csymbol encoding="text"
              definitionURL="http://www.sbml.org/sbml/symbols/time"> time </csymbol>
              <cn> 12 </cn></apply>
          </math>
        </trigger>
        <listOfEventAssignments>
          <eventAssignment variable="dose">
            <math xmlns="http://www.w3.org/1998/Math/MathML"><cn> 0 </cn></math>
          </eventAssignment>
        </listOfEventAssignments>
      </event>
    </listOfEvents>
  </model>
</sbml>
"""


def test_an_override_an_event_may_overwrite_is_disclosed_not_refused() -> None:
    """The gap docs/findings-note.md left open when the event guard was reverted.

    Refusing an override an event assigns to was measured to be wrong — an event overwrites its
    target only when its trigger fires, and three real shapes each moved the answer threefold under
    a refusal saying the override had no effect. What was left was a silence: the certificate
    published the override and said nothing about the event that might replace it. It says so now,
    without claiming the override *was* overwritten, which would need the trigger evaluated over
    the window rather than a name lookup.
    """
    from reprolith.certify import _events_overwriting

    warnings = _events_overwriting(_EVENT_MODEL, (("dose", 50.0),))
    assert len(warnings) == 1
    assert "event 'reset_at_12h' assigns to 'dose'" in warnings[0]
    assert "not evaluated" in warnings[0]


def test_an_override_no_event_touches_is_left_unqualified() -> None:
    """The check is targeted: the metformin model has two events and neither assigns to the dose
    parameter its 1000 mg claim overrides, so that certificate carries no caution."""
    from reprolith.certify import _events_overwriting

    assert _events_overwriting(_EVENT_MODEL, (("k", 0.2),)) == ()
    metformin = (
        Path(__file__).parent.parent
        / "datasets" / "worked_examples" / "Zake2021_metformin_human_single_PO.xml"
    ).read_text(encoding="utf-8")
    assert _events_overwriting(metformin, (("Metformin_Dose_in_Lumen_in_mg", 779.9),)) == ()


def test_the_caution_reaches_the_protocol_a_reader_sees() -> None:
    """A warning nothing publishes is not a disclosure."""
    from reprolith.certify import _run_protocol

    protocol = _run_protocol(
        duration=24.0, steps=480, read="[X] cmax", overrides=(("dose", 50.0),),
        overwritten=("caution: event 'reset_at_12h' assigns to 'dose', which this claim overrides"
                     " — whether it fires within the window was not evaluated",),
    )
    assert "overrides: dose=50.0" in protocol
    assert "caution: event 'reset_at_12h'" in protocol


def test_a_claim_taking_the_figure_band_has_to_name_what_read_the_figure() -> None:
    """The widening was escapable in the direction that flatters a reconstruction.

    A reading can only ever be recorded as `digitized-figure`, so a picture-read value cannot be
    judged as a printed number. The reverse was free: a claims record is a dict, and writing
    `"reference_kind": "digitized-figure"` beside a value cited to a paragraph took a scalar's pass
    threshold from 5% to 15% with no picture, no tool and no reading behind it — and the
    certificate then marked it `[figure-reading]` and gave a reader nothing to weigh.
    """
    record = {
        "claim_id": "peak", "quantity": "plasma Cmax", "species": "C", "reported": 4.2,
        "source_location": "Section 3, paragraph 2", "reference_kind": "digitized-figure",
    }
    with pytest.raises(ValueError, match="states no digitizer"):
        Claim.from_record(record)

    # Named, it is accepted — and the tool travels into what the certificate cites, because the
    # source location of a hand-written claim says nothing about how the value was read.
    named = Claim.from_record({**record, "digitizer": "WebPlotDigitizer 4.7"})
    assert named.cited_source == (
        "Section 3, paragraph 2 (read off the figure with WebPlotDigitizer 4.7)"
    )
    # And the printed number it always was needs nothing: the fence is only on the wider band.
    assert Claim.from_record({**record, "reference_kind": "numeric"}).cited_source == (
        "Section 3, paragraph 2"
    )


def test_a_reading_that_came_through_the_join_states_itself_and_is_not_asked_twice() -> None:
    """`attach_digitized_values` writes the figure, the tool and the reading's cost into the
    citation, so the claim built from it already says what read the figure. Requiring a separate
    field there would make the join lossy and print the tool twice.
    """
    from reprolith import attach_digitized_values, read_digitized_figure
    from reprolith.certify import CurveClaim
    from reprolith.dossier import DossierClaim

    joined = attach_digitized_values(
        [DossierClaim(id="c", quantity="[C]", conditions="", source_location="Figure 1, curve c",
                      reference_kind=ReferenceKind.DIGITIZED_FIGURE)],
        read_digitized_figure(json.dumps({
            "figure": "Figure 1", "digitizer": "WebPlotDigitizer 4.7",
            "x_axis": {"minimum": 0, "maximum": 10, "unit": "h"},
            "y_axis": {"minimum": 0, "maximum": 10, "unit": "nM"},
            "series": [{"claim": "c", "curve": "C", "points": [[0, 8.0], [5, 4.0], [10, 2.0]]}],
        })),
        times=[0.0, 5.0, 10.0],
    )[0]
    claim = CurveClaim(
        claim_id="c", quantity="[C]", species="C", reference=joined.reference_data,
        source_location=joined.source_location, duration=10.0, steps=2,
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    assert claim.cited_source == joined.source_location
    assert claim.cited_source.count("WebPlotDigitizer 4.7") == 1

    # What counts as "already stated" is the join's own phrase, not the tool's name appearing
    # somewhere in the citation. A citation that merely mentions the tool has not stated a reading,
    # and suppressing the statement on it would let the fence and the citation disagree.
    mentions = CurveClaim(
        claim_id="c", quantity="[C]", species="C", reference=(1.0, 2.0, 3.0),
        source_location="Figure 1, the curve WebPlotDigitizer 4.7 could not resolve",
        duration=10.0, steps=2, reference_kind=ReferenceKind.DIGITIZED_FIGURE,
        digitizer="WebPlotDigitizer 4.7",
    )
    assert mentions.cited_source.endswith("(read off the figure with WebPlotDigitizer 4.7)")


def test_a_figure_claim_with_nothing_behind_it_still_abstains_rather_than_being_refused() -> None:
    """The band is never consulted where there is no reference to consult it against.

    A document's plots are claims the paper stakes and never says the value of, so the dossier
    marks them `digitized-figure` with no data — the abstention this repository exists to publish.
    Demanding a digitizer for a reading nobody took would refuse it.
    """
    from reprolith.certify import CurveClaim

    unread = CurveClaim(
        claim_id="c", quantity="[C]", species="C", reference=(),
        source_location="SED-ML plot2D 'plot_0', curve 'c'", duration=10.0, steps=2,
        reference_kind=ReferenceKind.DIGITIZED_FIGURE,
    )
    assert unread.cited_source == "SED-ML plot2D 'plot_0', curve 'c'"


def test_a_scalar_read_off_a_figure_walks_to_a_certificate_that_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the figure path, which nothing walked end to end.

    A curve read off a picture has a walk (`tests/test_digitized_figure_end_to_end.py`). A *scalar*
    read off one — a peak height, a Cmax a paper plots rather than prints — had a tolerance, a
    reference kind, a render marker and now a fence demanding the tool that read it, and no test
    that carried one from a claim to a rendered certificate. Each piece was covered; the join was
    not.

    Three things have to survive that join, and the middle one is the reason the fence exists: the
    marker, the widened band, and the statement of what read the figure. A reader seeing
    `[figure-reading]` and `<=0.15` where a printed number gets `<=0.05` can weigh the verdict only
    if the certificate also says the number came off a picture and which tool took it off.
    """
    import reprolith.certify as certify_module
    from reprolith import (
        Claim,
        ComparisonMethod,
        EnginePin,
        PaperIdentity,
        ReferenceKind,
        RunMetadata,
        certify_model,
        default_tolerance,
        render_human,
    )

    times = tuple(float(i) for i in range(11))
    monkeypatch.setattr(
        certify_module, "simulate", lambda *a, **k: (times, tuple(4.6 for _ in times))
    )
    certificate = certify_model(
        "<sbml/>",
        paper=PaperIdentity(title="A peak the paper plots", doi="10.0/fig"),
        engine_pin=EnginePin(engine="test-engine", version="0.0.0"),
        duration=10.0,
        steps=10,
        claims=[Claim(
            claim_id="peak", quantity="plasma Cmax", species="C", reported=4.2,
            source_location="Figure 3A, the upper curve's maximum",
            reference_kind=ReferenceKind.DIGITIZED_FIGURE,
            digitizer="WebPlotDigitizer 4.7",
        )],
    )
    (assessment,) = certificate.assessments
    assert assessment.verdict.value == "reproduced"

    printed = render_human(certificate, RunMetadata(
        created_at="2026-09-01T00:00:00Z", actor="a-test", tool_version="0.0.1"
    ))
    assert "[figure-reading]" in printed
    # The band a printed number would have been judged in is 0.05; this is three times it, and the
    # certificate has to say both the number and why it is that number.
    assert "reproduced<=0.15" in printed
    assert "read off the figure with WebPlotDigitizer 4.7" in printed
    # And the band is doing work here rather than decorating a pass that would have held anyway:
    # 4.6 against a reported 4.2 is 9.5%, inside the figure band's 15% and outside the 5% the same
    # number would have been held to had it been printed. That is the case the marker exists for.
    assert 0.09 < float(assessment.discrepancy.split()[-1]) < 0.10, assessment.discrepancy
    printed_band = default_tolerance(
        ComparisonMethod.SCALAR_RELATIVE_ERROR, ReferenceKind.NUMERIC
    )
    assert printed_band.reproduced_within == 0.05
