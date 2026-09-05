#!/usr/bin/env python3
"""Break a guard on purpose and check that a test notices (the discipline loop's 8.2 method).

A test that passes tells you nothing about whether it would fail. This runs the other direction:
each entry below removes one guard from a *copy* of the package and asserts that the named tests go
red. A guard whose removal nobody notices is a guard with no test, however green the suite looks.

Every mutation here corresponds to a defect that was real once — a term silently dropped, a schema
published and not enforced, an inert attribute read as a value — so this is also the list of things
this repository has already been wrong about.

Two ways to fail, and the second matters more than it looks:

* a mutation **survives**: the guard has no test, or the test does not reach the case that makes it
  load-bearing. One of these was found that way — the manuscript check's suppression of a
  model-computed parameter had a test that passed with the branch deleted, because it never gave
  the document a value to run;
* a mutation's **anchor is gone**: the code moved and this list did not. Reported as a failure, not
  skipped. A checker that quietly counts fewer things than it did last week is the shape of defect
  it exists to catch.

Needs the engine extra (the tests it runs do). Run from the repo root:

    python scripts/mutation_check.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: ``(what removing it means, module, (anchor, replacement), tests that must go red)``.
#:
#: One shape does not belong here: a guard whose absence makes a test **hang** rather than fail.
#: `supersession.chain` breaks on a digest it has already seen, and `tests/test_supersession.py`
#: injects a cycle to prove it — remove the break and that test loops forever, which stalls this
#: checker instead of reporting anything. The invariant is real and tested; it is the *mutation*
#: that is unusable, because this harness runs a suite to completion to decide what a guard is
#: worth.
MUTATIONS: list[tuple[str, str, tuple[str, str], list[str]]] = [
    (
        "a budgeted certificate takes the clean pass while claims went unattempted",
        "certificate.py",
        (
            "        if qualified or load_bearing or awaiting or unattempted:",
            "        if qualified or load_bearing or awaiting:",
        ),
        ["tests/test_budgeted_certificate.py"],
    ),
    (
        "a certificate both judges a claim and says it never attempted it",
        "certificate.py",
        ("    if selection is None:\n        return", "    return"),
        ["tests/test_budgeted_certificate.py"],
    ),
    (
        "a certificate's selection is left out of the content it is digested from",
        "model.py",
        (
            '            **({} if self.selection is None else {"selection": self.selection.to_dict()}),',
            "",
        ),
        ["tests/test_budgeted_certificate.py"],
    ),
    (
        "a footprint reaches the selector without saying whether a walk or a person produced it",
        "dossier.py",
        ("        if self.footprint and self.footprint_origin is None:", "        if False:"),
        ["tests/test_claim_selection.py"],
    ),
    (
        "an LP bound is published at the machine's own last places",
        "corroboration.py",
        ("    distance = max(measured, _LP_NOISE_FLOOR)", "    distance = measured"),
        ["tests/test_fba_corroboration.py"],
    ),
    (
        "a partial SAT model is compared against a complete state",
        "corroboration.py",
        ("    if missing:", "    if False:"),
        ["tests/test_logical_corroboration.py"],
    ),
    (
        "the corroboration draws report the best measurement instead of the worst",
        "corroboration.py",
        (
            "    distance = max(max(measure() for _ in range(draws)), _CURVE_NOISE_FLOOR)",
            "    distance = max(min(measure() for _ in range(draws)), _CURVE_NOISE_FLOOR)",
        ),
        ["tests/test_corroboration.py"],
    ),
    (
        "the manuscript check reads a parameter the model's own math determines",
        "manuscript.py",
        ("            if parameter in computed:", "            if False:"),
        ["tests/test_manuscript_mismatch.py"],
    ),
    (
        "the manuscript check calls an output unrecorded on a document it cannot read",
        "manuscript.py",
        (
            "elif observations_readable and claim.species not in observed:",
            "elif claim.species not in observed:",
        ),
        ["tests/test_manuscript_mismatch.py"],
    ),
    (
        "the MCP server stops enforcing the input schema it publishes",
        "mcp_server.py",
        ("            _validate_arguments(name, arguments)", "            pass"),
        ["tests/test_mcp_server.py"],
    ),
    (
        "the MCP server reaches .get on positional params",
        "mcp_server.py",
        ("        if not isinstance(params, dict):", "        if False:"),
        ["tests/test_mcp_server.py"],
    ),
    (
        "a paper lookup naming no identifier answers 'no certificates'",
        "mcp_server.py",
        ("    if not named:", "    if False:"),
        ["tests/test_mcp_server.py"],
    ),
    (
        "the archive check counts the claims it was handed as checked",
        "presubmission.py",
        ('        found["manuscript_claims_checked"] = len(claims)', "        pass"),
        ["tests/test_archive_check.py"],
    ),
    (
        "the archive check judges a constraint-based model as a time course",
        "presubmission.py",
        ("    if not targetable and not not_a_time_course:", "    if not targetable:"),
        ["tests/test_archive_check.py", "tests/test_archive_check_across_classes.py"],
    ),
    (
        "the dossier comparison forgets that an initial assignment makes a value inert",
        "sbml.py",
        (
            "        for i in range(model.getNumInitialAssignments())\n    } - rule_determined",
            "        for i in range(0)\n    } - rule_determined",
        ),
        ["tests/test_ingest.py"],
    ),
    (
        "a population publishes an envelope its ensemble cannot resolve",
        "population.py",
        ("    if subjects < _SPREAD_IS_EVIDENCE:", "    if False:"),
        ["tests/test_population_simulation.py"],
    ),
    (
        "a percentile no ensemble that size can express is reported as one",
        "population.py",
        ("        if subjects * tail <= 100.0:", "        if False:"),
        ["tests/test_population_simulation.py"],
    ),
    (
        "the figure check stops asking whether the reading is paired with a real curve",
        "cli.py",
        (
            '    faults = pairing_faults(claims, series, carrier="your document") '
            "if claims is not None else ()",
            "    faults = ()",
        ),
        ["tests/test_cli.py"],
    ),
    (
        "the figure check stops asking whether the reading covers the run",
        "cli.py",
        (
            '    short = window_faults(series, windows, carrier="your document") if windows else ()',
            "    short = ()",
        ),
        ["tests/test_cli.py"],
    ),
    (
        "the template writes two of a document's plots into one file",
        "digitization.py",
        ("    if panel is None and len(panels) > 1:", "    if False:"),
        ["tests/test_cli.py"],
    ),
    (
        "a file holding two panels is read against one panel's axes",
        "cli.py",
        (
            '    faults += panel_faults(series, panels, carrier="your document")',
            "    faults += ()",
        ),
        ["tests/test_cli.py"],
    ),
    (
        "one claim read off two panels keeps whichever file was passed last",
        "digitization.py",
        (
            "    for claim_id in sorted({c for c in paired if paired.count(c) > 1}):",
            "    for claim_id in []:",
        ),
        ["tests/test_digitization.py", "tests/test_cli.py"],
    ),
    (
        "a reading is taken to cover a window it stops short of",
        "digitization.py",
        (
            "        if any(low <= start and high >= end for start, end in windows):",
            "        if True:",
        ),
        ["tests/test_digitization.py"],
    ),
    (
        "the track record page keeps a clean sheet the committed report contradicts",
        "agreement.py",
        (
            '        if actual == "blocked" and expected != actual:  # a disagreement that abstained',
            "        if expected != actual:",
        ),
        ["tests/test_self_validation_doc.py"],
    ),
    (
        "the parameter check counts only what it was handed and never what it was not",
        "manuscript_values.py",
        (
            "        sorted(name for name in declared if name not in determined and name not in paired)",
            "        sorted(name for name in [] if name not in determined and name not in paired)",
        ),
        ["tests/test_parameter_values.py"],
    ),
    (
        "a figure read in mg becomes the reference for a curve the model reads in nmol",
        "digitization.py",
        (
            "        if declared == UNSTATED_UNIT or not _units_known_to_differ(stated, declared):",
            "        if True:",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "a figure read on one clock is placed on a run that keeps another",
        "digitization.py",
        (
            "        if not _units_known_to_differ(stated, declared):\n            continue",
            "        if True:\n            continue",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "a claim's value is compared against a model output in another unit",
        "manuscript_values.py",
        (
            "        elif _units_differ(stated, declared):\n            results.append(UnitCheck(\n                claim_id, stated, declared, False,",
            "        elif False:\n            results.append(UnitCheck(\n                claim_id, stated, declared, False,",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "an area under the curve is read in the unit of the peak, with no time in it",
        "manuscript_values.py",
        (
            '    over = f"{substance} * {time}" if metric == "auc" else substance',
            "    over = substance",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "the prefix is dropped, so a paper's millilitres read as the model's litres",
        "manuscript_values.py",
        (
            "            return (prefixed * 10.0 ** power * carried, kind)",
            "            return (prefixed * carried, kind)",
        ),
        ["tests/test_parameter_values.py"],
    ),
    (
        "a paper's litres are compared against a model's millilitres as if they were the same",
        "manuscript_values.py",
        (
            "        if stated and units != UNSTATED_UNIT and _units_differ(stated, units):",
            "        if False:",
        ),
        ["tests/test_parameter_values.py"],
    ),
    (
        "the parameters template fills in the model's own value as the paper's",
        "manuscript_values.py",
        (
            '            "reported": None,\n            "reported_units": "",',
            '            "reported": _value,\n            "reported_units": "",',
        ),
        ["tests/test_parameter_values.py"],
    ),
    (
        "an unpaired proposal reads as a model that does not carry its paper's values",
        "manuscript_values.py",
        (
            "        if not identifier:\n            # A row from `params-propose` carries",
            "        if False:\n            # A row from `params-propose` carries",
        ),
        ["tests/test_parameter_values.py"],
    ),
    (
        "the input check reads the parameter list again and not the volumes or initial conditions",
        "manuscript_values.py",
        (
            '    "compartment": ("size",),\n    "species": ("initialAmount", "initialConcentration"),\n',
            "",
        ),
        ["tests/test_parameter_values.py"],
    ),
    (
        "a claim value matched in seven cells reads exactly like one matched in one",
        "manuscript_values.py",
        (
            "        others = occurrences - 1",
            "        others = 0",
        ),
        ["tests/test_manuscript_reference_values.py"],
    ),
    (
        "a row that states no metric is judged against the peak column anyway",
        "manuscript_values.py",
        (
            "    if \"metric\" not in record:\n        return \"cmax\"",
            "    if True:\n        return \"cmax\"",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "a claim labelled with a unit its own cited table does not print reads as checked",
        "manuscript_values.py",
        (
            "        if _units_known_to_differ(stated, printed):",
            "        if False:",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "the exported archive leaves without saying what it is or where it came from",
        "export.py",
        (
            "    _provenance_notes(document, bundle)",
            "    pass",
        ),
        ["tests/test_export.py"],
    ),
    (
        "the linter compares an agent's reference against a model reading another quantity",
        "linter.py",
        (
            "    refusal = _units_refusal(sbml, species, reference_units)",
            "    refusal = None",
        ),
        ["tests/test_linter.py"],
    ),
    (
        "a candidate is proposed with a unit nothing could read as one",
        "claim_candidates.py",
        (
            '    return tail if tail and _canonical_composite(tail) is not None else ""',
            "    return tail",
        ),
        ["tests/test_claim_candidates.py"],
    ),
    (
        "the dossier page counts the word 'unstated' as a stated unit",
        "render.py",
        (
            '        stated = sum(1 for item in countable if item.get("unit") not in (None, "", UNSTATED_UNIT))',
            '        stated = sum(1 for item in countable if item.get("unit"))',
        ),
        ["tests/test_render.py"],
    ),
    (
        "the author-facing report is served to its author as a machine view",
        "cli.py",
        (
            "    print(render_presubmission_human(cert))",
            "    _print_json(query.presubmission(args.digest))",
        ),
        ["tests/test_cli.py"],
    ),
    (
        "a parameter an initialAssignment makes inert is ingested at the number in its attribute",
        "ingest.py",
        (
            "        elif parameter.getId() not in assignment_targets | initial_assignment_targets:",
            "        elif parameter.getId() not in assignment_targets:",
        ),
        ["tests/test_ingest.py"],
    ),
    (
        "an AUC that moves with the sample grid is certified rather than abstained on",
        "certify.py",
        (
            "            if not established:",
            "            if False:",
        ),
        ["tests/test_auc_convergence.py"],
    ),
    (
        "a load-bearing assumption no claim was flagged for still certifies a clean pass",
        "certificate.py",
        (
            "        if qualified or load_bearing or awaiting or unattempted:",
            "        if qualified or unattempted:",
        ),
        ["tests/test_certificate.py"],
    ),
    (
        "a scope statement reworded to say something else is minted without complaint",
        "scope.py",
        (
            "        if (self.machine, self.human) != (SCOPE_MACHINE, SCOPE_HUMAN):",
            "        if False:",
        ),
        ["tests/test_scope.py"],
    ),
    (
        "an archive member is decompressed however large it expands to",
        "omex.py",
        (
            "    if declared > _MAX_MEMBER_BYTES:",
            "    if False:",
        ),
        ["tests/test_omex.py"],
    ),
    (
        "the public page publishes a verdict with no measurement behind it",
        "render.py",
        (
            '            f\'<details class="claims"><summary>how close each claim came \'',
            '            f\'<details class="claims" hidden><summary>\'',
        ),
        ["tests/test_render.py"],
    ),
    (
        "the human certificate publishes a pass with no measurement behind it",
        "render.py",
        (
            '            lines.append(f"      measured: {a[\'discrepancy\']}")',
            "            pass",
        ),
        ["tests/test_render.py"],
    ),
    (
        # The branch moved to `query.corroboration_summary` when the terminal and the agent
        # surface started answering from the same computation as the page. This entry went on
        # naming render.py and reported STALE — which is the checker working, and nobody was
        # running it: the registry, the CLI and MCP all read this one branch now, so the tests it
        # is held by are the surface's rather than the renderer's alone.
        "the registry omits the classes no second engine ever checked",
        "query.py",
        (
            "            unchecked.append(model_class)",
            "            pass",
        ),
        ["tests/test_corroboration_surface.py"],
    ),
    (
        "the verdict summary names the qualified claims and not what qualified them",
        "query.py",
        (
            "                if asm.load_bearing or asm.verification_item",
            "                if False",
        ),
        ["tests/test_query.py"],
    ),
    (
        "a false pass and an over-strict verdict are reported under the same word",
        "agreement.py",
        (
            '                if _STRENGTH.index(actual) > _STRENGTH.index(expected)',
            "                if True",
        ),
        ["tests/test_agreement.py"],
    ),
    (
        "the fix list emits one assumption row per claim it withheld a pass from",
        "presubmission.py",
        (
            "    if qualified:",
            "    if False:",
        ),
        ["tests/test_presubmission.py"],
    ),
    (
        "a claim takes the figure band's widening without naming what read the figure",
        "certify.py",
        (
            "    if judged and reference_kind is ReferenceKind.DIGITIZED_FIGURE and not stated:",
            "    if False:",
        ),
        ["tests/test_certify.py"],
    ),
    (
        "the certificate quotes a reading's cost over the whole file, not the run it judged",
        "digitization.py",
        (
            '                f"{reading.source_line(window=(min(times), max(times)))}"',
            '                f"{reading.source_line()}"',
        ),
        ["tests/test_digitization.py"],
    ),
    (
        "the figure check costs a reading over the whole file, not the run it will be judged on",
        "cli.py",
        (
            "    costs = [_windowed_cost(s, windows) for s in series]",
            "    costs = [interpolation_cost(s) for s in series]",
        ),
        ["tests/test_cli.py"],
    ),
    (
        "a curve plotted from shipped data becomes a result the model must reproduce",
        "sedml.py",
        ("            if generator.data_sources:", "            if False:"),
        ["tests/test_sedml_data.py"],
    ),
    (
        "a spreadsheet's byte-order mark hides the first data column",
        "sedml.py",
        ('cell.strip().lstrip("\\ufeff")', "cell.strip()"),
        ["tests/test_sedml_data.py"],
    ),
    (
        "export answers a path it cannot write with a traceback",
        "cli.py",
        ("    except OSError as unwritable:", "    except ZeroDivisionError as unwritable:"),
        ["tests/test_cli.py"],
    ),
    (
        "the spatial reader drops a drift term",
        "sbml.py",
        ("        if parameter_plugin.isSetAdvectionCoefficient():", "        if False:"),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "the spatial reader drops a decay reaction",
        "sbml.py",
        (
            "        decay[decaying] = _mass_action_rate(reaction.getKineticLaw(), {decaying: 1})",
            "        decay[decaying] = 0.0",
        ),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "the spatial reader takes a stated domain shape as its bounding box",
        "sbml.py",
        ("    if geometry.getNumGeometryDefinitions() > 0:", "    if False:"),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "the spatial reader reads an initial value the model overrides",
        "sbml.py",
        ("        if name in overridden:", "        if False:"),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "the spatial reader spreads a species the model holds fixed",
        "sbml.py",
        (
            "        if entity.getBoundaryCondition() or entity.getConstant():",
            "        if False:",
        ),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "the band comparison names the envelope whose grid does not match",
        "oracle.py",
        ("        if expected != got:", "        if False:"),
        ["tests/test_population_end_to_end.py"],
    ),
    (
        "params-check blames the pairing for a model that names nothing",
        "cli.py",
        ("        if unnamed:", "        if False:"),
        ["tests/test_cli.py"],
    ),
    (
        "a data series the reader dropped is never mentioned to the author",
        "presubmission.py",
        ("        for message in unread:", "        for message in ():"),
        ["tests/test_archive_check.py"],
    ),
    (
        "the data reader drops a source without recording why",
        "sedml.py",
        ("    return tuple(_read_data(sedml, files)[1])", "    return ()"),
        ["tests/test_sedml_data.py"],
    ),
    (
        "a curve bound is published from digits that move between draws and machines",
        "corroboration.py",
        (
            "    distance = max(max(measure() for _ in range(draws)), _CURVE_NOISE_FLOOR)",
            "    distance = max(measure() for _ in range(draws))",
        ),
        ["tests/test_corroboration.py"],
    ),
    (
        "an unreadable SED-ML task shrinks the adoptable-run count and says nothing",
        "presubmission.py",
        ("        if unnamed_sedml:", "        if False:"),
        ["tests/test_archive_check.py"],
    ),
    (
        "the archive check passes a model that names none of its own quantities",
        "presubmission.py",
        # Anchored on the line below it too: a bare `if unnamed:` matches a second site inside
        # `_unnamed_declarations_in`, and a guard that can silently move to a different branch
        # tests whatever it lands on rather than what it names.
        (
            '        if unnamed:\n            listed = ", ".join(unnamed[:5])',
            '        if False:\n            listed = ", ".join(unnamed[:5])',
        ),
        ["tests/test_archive_check.py"],
    ),
    (
        "an unreadable archive repeats a dataclass's complaint instead of the author's fault",
        "presubmission.py",
        ("        if unnamed_by_member:", "        if False:"),
        ["tests/test_archive_check.py"],
    ),
    (
        "the model writer accepts a name SBML drops, and emits a species with no id",
        "sbml.py",
        ("    if unusable:", "    if False:"),
        ["tests/test_sbml.py"],
    ),
    (
        "the network writer accepts a species name SBML cannot hold",
        "sbml.py",
        ("    invalid = [name for name in species if not _SBML_ID.match(name)]",
         "    invalid = []"),
        ["tests/test_stochastic_corroboration.py"],
    ),
    (
        "the degenerate ensemble branch names a build string as an engine",
        "corroboration.py",
        (
            "            engines=(degenerate.engine, ROADRUNNER_SSA_ENGINE),",
            "            engines=(_reprolith_build(degenerate), ROADRUNNER_SSA_ENGINE),",
        ),
        ["tests/test_stochastic_corroboration.py"],
    ),
    (
        "the ensemble corroboration compares two samplers that model different systems",
        "corroboration.py",
        ("    if higher_order:", "    if False:"),
        ["tests/test_stochastic_corroboration.py"],
    ),
    (
        "a count of standard errors is published on the curve classes' distance scale",
        "corroboration.py",
        (
            "            return math.ceil(self.distance * 10.0) / 10.0",
            "            pass",
        ),
        ["tests/test_stochastic_corroboration.py"],
    ),
    (
        "the network handed to the second engine runs at a different rate than this one",
        "sbml.py",
        (
            "        parameter.setValue(reaction.rate / stoichiometric_factor)",
            "        parameter.setValue(reaction.rate)",
        ),
        ["tests/test_stochastic_corroboration.py"],
    ),
    (
        "the LP corroboration names scipy's build but not the code that formed the program",
        "corroboration.py",
        (
            "        versions=(_reprolith_build(pin), cobrapy_version),",
            "        versions=(pin.version, cobrapy_version),",
        ),
        ["tests/test_corroboration_contract.py"],
    ),
    (
        "the spatial reference is integrated over a window the certificate does not run",
        "corroboration.py",
        ("    duration = dt * steps", "    duration = dt * steps * 2"),
        ["tests/test_spatial_corroboration.py"],
    ),
    (
        "the spatial reference drops the decay term the class solves",
        "corroboration.py",
        (
            "        lambda _t, u: operator.dot(u) - decay * u,",
            "        lambda _t, u: operator.dot(u),",
        ),
        ["tests/test_spatial_corroboration.py"],
    ),
    (
        "an ensemble agreement is read out on the deterministic classes' scale",
        "query.py",
        (
            '        return f"all engine-independent within {float(bound):.1f} combined standard errors{seen}"',
            '        return f"all engine-independent to {float(bound):.0e}"',
        ),
        ["tests/test_stochastic_corroboration.py"],
    ),
]


def main() -> int:
    survivors: list[str] = []
    stale: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for meaning, module, (anchor, replacement), tests in MUTATIONS:
            package = Path(scratch) / "python"
            shutil.rmtree(package, ignore_errors=True)
            shutil.copytree(REPO / "python", package)
            target = package / "reprolith" / module
            source = target.read_text(encoding="utf-8")
            if anchor not in source:
                stale.append(f"{module}: {meaning}")
                print(f"STALE     {meaning}")
                continue
            target.write_text(source.replace(anchor, replacement, 1), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", *tests, "-q", "--no-header", "-x"],
                capture_output=True,
                text=True,
                cwd=REPO,
                env={**os.environ, "PYTHONPATH": str(package)},
            )
            if result.returncode:
                print(f"killed    {meaning}")
            else:
                survivors.append(meaning)
                print(f"SURVIVED  {meaning}")

    if stale:
        print(f"\n{len(stale)} mutation(s) no longer apply — the code moved and this list did not.")
        print("Update the anchor or delete the entry; a checker that quietly checks less is the")
        print("defect it exists to catch.")
    if survivors:
        print(f"\n{len(survivors)} guard(s) can be removed with every test still passing:")
        for meaning in survivors:
            print(f"  - {meaning}")
    if not stale and not survivors:
        print(f"\nall {len(MUTATIONS)} guards are held by a test that fails without them")
    return 1 if (stale or survivors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
