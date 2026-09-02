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
MUTATIONS: list[tuple[str, str, tuple[str, str], list[str]]] = [
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
        "the registry omits the classes no second engine ever checked",
        "render.py",
        (
            "            unchecked.append(model_class)",
            "            pass",
        ),
        ["tests/test_render.py"],
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
