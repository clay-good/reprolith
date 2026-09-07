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
  it exists to catch;
* a mutation's **anchor is ambiguous**: it matches more than one place, so the replacement lands on
  whichever comes first and the entry owning the other site stops being checked. Also a failure —
  a quote that is not unique is a guard pointed at the wrong text.

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
        "the certificate a person reads cannot tell this engine's limit from the paper's omission",
        "render.py",
        ('            ours = asm.get("author_can_close", True) is False',
         "            ours = False"),
        ["tests/test_verification_escalation.py"],
    ),
    (
        "the documented gap-closing route cannot say a gap is this engine's limit",
        "reconstruction.py",
        ("        author_can_close=author_can_close,\n    )", "    )"),
        ["tests/test_reconstruction.py"],
    ),
    (
        "a population's own ensemble is billed to the author as a value their paper could state",
        "certify.py",
        ("            author_can_close=False,\n        )\n        for claim in claims",
         "        )\n        for claim in claims"),
        ["tests/test_ensemble_assumptions.py"],
    ),
    (
        "the fix list's summary row asks for values the row above it says nothing can clear",
        "presubmission.py",
        ('                "fix": _rollup_fix(named),',
         '                "fix": "state the assumed values listed above explicitly, so these '
         'need not rest on them",'),
        ["tests/test_ensemble_assumptions.py"],
    ),
    (
        "a queue item id the certificate itself names is replaced by a derived hash",
        "verification.py",
        (
            "    if assumption.verification_item:\n        return assumption.verification_item",
            "    if False:\n        return assumption.verification_item",
        ),
        ["tests/test_verification_escalation.py"],
    ),
    (
        "one solver limitation asked by three claims becomes three items to answer three times",
        "verification.py",
        ('    return f"verify:{question_fingerprint(assumption)[:12]}"',
         '    return f"verify:{assumption.id}@{question_fingerprint(assumption)[:12]}"'),
        ["tests/test_verification_escalation.py"],
    ),
    (
        "this engine's own limits are ranked as questions waiting on an expert",
        "verification.py",
        ("            if assumption.author_can_close:", "            if True:"),
        ["tests/test_verification_escalation.py"],
    ),
    (
        "an assumption the certificate says is under review is left out of the queue",
        "verification.py",
        (
            "            if not assumption.load_bearing and not assumption.verification_item:\n"
            "                continue\n            item_id = _item_id(assumption)",
            "            if not assumption.load_bearing:\n"
            "                continue\n            item_id = _item_id(assumption)",
        ),
        ["tests/test_verification_escalation.py"],
    ),
    (
        "the gap report says a value is under review only where somebody wrote an id by hand",
        "render.py",
        (
            "        awaits = asm.verification_item is not None or "
            "(asm.load_bearing and asm.author_can_close)",
            "        awaits = asm.verification_item is not None",
        ),
        ["tests/test_verification_escalation.py"],
    ),
    (
        "a backlog blocker is ranked by every block in an entry's history, not its current one",
        "catalog.py",
        (
            "                (t for t in reversed(entry.history) "
            "if t.to_state is LifecycleState.BLOCKED),",
            "                (t for t in entry.history if t.to_state is LifecycleState.BLOCKED),",
        ),
        ["tests/test_backlog_blockers.py"],
    ),
    (
        "a window the run does not reach reads as an area of zero or a traceback",
        "certify.py",
        ("    if len(kept) < 2:", "    if False:"),
        ["tests/test_certify.py"],
    ),
    (
        "a limit of Reprolith's own run heads the author's fix list as their most urgent job",
        "presubmission.py",
        (
            '        if (assessment.fault_hypothesis or "") == Fault.METHOD.value:',
            "        if False:",
        ),
        ["tests/test_presubmission.py"],
    ),
    (
        "an assumption the author closes by correcting is answered with 'state it explicitly'",
        "presubmission.py",
        ("                        asm.closed_by\n", '                        "" or\n'),
        ["tests/test_presubmission.py"],
    ),
    (
        "a verdict the run's own sampling could flip is published as if the model decided it",
        "certify.py",
        (
            "        settled = settled and change <= nearest_boundary",
            "        settled = settled",
        ),
        ["tests/test_auc_convergence.py"],
    ),
    (
        "a time to peak is read in the output's unit rather than in the model's clock",
        "manuscript_values.py",
        (
            '    if metric == "tmax":',
            "    if False:",
        ),
        ["tests/test_claim_units.py"],
    ),
    (
        "an area the paper took over one dosing day is judged over the whole run",
        "certify.py",
        (
            "    times, values = _window_of(times, values, window)",
            "    times, values = times, values",
        ),
        ["tests/test_certify.py", "tests/test_twice_daily_shortfalls.py"],
    ),
    (
        "an exported document states a whole-run area for a claim taken over part of it",
        "export.py",
        ("    if step.window is not None:", "    if False:"),
        ["tests/test_export.py"],
    ),
    (
        "the not-ready sentence describes one cause while the flag was set by four",
        "presubmission.py",
        (
            '    return [text for key, text in _NOT_READY_REASONS if present[key]]',
            '    return [text for key, text in _NOT_READY_REASONS if present["gaps"]]',
        ),
        ["tests/test_presubmission.py", "tests/test_surface_honesty.py"],
    ),
    (
        "the parameters check words its refusals for the other file, and names the wrong command",
        "cli.py",
        (
            '_claim_records(Path(args.parameters), args.accession, holds="parameters")',
            "_claim_records(Path(args.parameters), args.accession)",
        ),
        ["tests/test_cli.py"],
    ),
    (
        "a template replaces work the author filled in by hand and prints a plain success line",
        "cli.py",
        (
            '    return ", replacing what was there" if replaced else ""',
            '    return ""',
        ),
        ["tests/test_cli.py"],
    ),
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
        ('    if missing:\n        raise ValueError(\n            "the independent solver returned a model that leaves "',
         '    if False:\n        raise ValueError(\n            "the independent solver returned a model that leaves "'),
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
        ("        replaced = _wrote(out, archive)\n    except OSError as unwritable:",
         "        replaced = _wrote(out, archive)\n    except ZeroDivisionError as unwritable:"),
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
        ("    operator = diags([off, main, off], [-1, 0, 1], format=\"csc\") * (diffusivity / (dx * dx))\n    duration = dt * steps",
         "    operator = diags([off, main, off], [-1, 0, 1], format=\"csc\") * (diffusivity / (dx * dx))\n    duration = dt * steps * 2"),
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
    # --- measuring what the engine's own limits cost, 2026-09-06 --------------------------------
    (
        "the boundary's cost is reported from the alternative that moves it least, understating it",
        "spatial.py",
        ("    worst = max(alternatives, key=lambda name: abs(alternatives[name] - judged))",
         "    worst = min(alternatives, key=lambda name: abs(alternatives[name] - judged))"),
        ["tests/test_spatial_boundaries.py"],
    ),
    (
        "a per-claim number in the boundary basis splits one solver limit into three questions",
        "spatial.py",
        ("            basis=_BOUNDARY_BASIS,", "            basis=_BOUNDARY_BASIS + claim.claim_id,"),
        ["tests/test_spatial_boundaries.py"],
    ),
    (
        "the zero-flux wall is the only one, so a Dirichlet model runs under Neumann walls",
        "spatial.py",
        ('    if boundary == "periodic":\n        return current[i - 1], current[(i + 1) % n]',
         "    if False:\n        return current[i - 1], current[(i + 1) % n]"),
        ["tests/test_spatial_boundaries.py"],
    ),
    (
        "an absorbing wall is fed a neighbour but never actually held at its value",
        "spatial.py",
        ("            nxt[0] = nxt[-1] = boundary_value", "            pass"),
        ["tests/test_spatial_boundaries.py"],
    ),
    (
        "the ensemble's sampling noise is reported only when it is too large to decide anything",
        "stochastic.py",
        ("    sem = math.sqrt(variance / trajectories)\n    return abs(sem / reported_mean), tol.reproduced_within",
         "    return None"),
        ["tests/test_stochastic.py"],
    ),
    (
        "a claim that states its own wall is still qualified for a choice nobody made for it",
        "spatial.py",
        ("    return claim.assumption_qualified and claim.wall_is_reprolith_s",
         "    return claim.assumption_qualified"),
        ["tests/test_spatial_boundaries.py"],
    ),
    (
        "the wall a claim states is dropped and the run uses this engine's default instead",
        "spatial.py",
        ("                boundary=claim.wall, boundary_value=claim.boundary_value,", ""),
        ["tests/test_spatial_boundaries.py"],
    ),
    (
        "a stated Dirichlet wall is read from the file and its held value thrown away",
        "sbml.py",
        ('                boundary, boundary_value = "dirichlet", float(parameter.getValue())',
         '                boundary, boundary_value = "dirichlet", 0.0'),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "a file asking for two different walls is run under whichever was read last",
        "sbml.py",
        ("            if boundaries and boundaries[-1] != (boundary, boundary_value):",
         "            if False:"),
        ["tests/test_spatial_ingest.py"],
    ),
    (
        "a decay length is qualified for a boundary that is the model rather than a choice",
        "spatial.py",
        ("predicted=measured,\n        tolerance=claim.tolerance,\n        attribution=claim.shortfall or undetermined_shortfall(claim.quantity),\n    )",
         "predicted=measured,\n        tolerance=claim.tolerance,\n        attribution=claim.shortfall or undetermined_shortfall(claim.quantity),\n        assumption_qualified=True,\n    )"),
        ["tests/test_spatial_gradient_claim.py"],
    ),
    (
        "a window no exponential can be fitted over publishes a slope as a length",
        "spatial.py",
        ("    except ValueError as unfittable:\n        return not_evaluable(",
         "    except ValueError as unfittable:\n        raise unfittable from None\n    if False:\n        return not_evaluable("),
        ["tests/test_spatial_gradient_claim.py"],
    ),
    (
        "a certificate is published for a paper this class judged nothing of",
        "spatial.py",
        ("    if not assessments:\n        raise ValueError(", "    if False:\n        raise ValueError("),
        ["tests/test_spatial_gradient_claim.py"],
    ),
    (
        "the fitting window a decay length depends on is left off the certificate",
        "spatial.py",
        ('f"[{claim.fit_from}, {claim.fit_to}); Dirichlet source at x=0 and a zero-flux far "',
         'f"[a window); Dirichlet source at x=0 and a zero-flux far "'),
        ["tests/test_spatial_gradient_claim.py"],
    ),
    (
        "a front that ran out of domain is reported as a front that never existed",
        "spatial.py",
        ("        ran_out = any(profile[-1] > claim.level for profile in readings)",
         "        ran_out = False"),
        ["tests/test_spatial_front_claim.py"],
    ),
    (
        "how far a KPP front is from its asymptote is left off the certificate",
        "spatial.py",
        ('f"identical window this speed still changes by {drift:.3e} "',
         'f"identical window this speed is what it is "'),
        ["tests/test_spatial_front_claim.py"],
    ),
    (
        "a front speed is measured from the initial condition rather than between two readings",
        "spatial.py",
        ("    speed = (middle - start) / window",
         "    speed = middle / (claim.settle_steps + claim.measure_steps) / claim.dt"),
        ["tests/test_spatial_front_claim.py"],
    ),
    # --- the collaboration surface, 2026-09-06 -------------------------------------------------
    # Twelve guards from one day's work. Every one was hand-mutated when it was written and none
    # was in this list, which is the gap this file exists to close: a guard proved once by hand is
    # a guard nothing checks next week.
    (
        "an expert appears to settle a question the same report says no expert decision closes",
        "verification.py",
        ("        if item.id not in answerable:", "        if False:"),
        ["tests/test_verification_decisions.py"],
    ),
    (
        "a decision keeps applying after the question under its id was reworded",
        "verification.py",
        ("        elif current != decision.question_fingerprint:", "        elif False:"),
        ["tests/test_verification_decisions.py"],
    ),
    (
        "a decision naming nothing standing is dropped instead of reported",
        "verification.py",
        ('        if current is None:\n            orphaned.append(',
         '        if current is None:\n            [].append('),
        ["tests/test_verification_decisions.py"],
    ),
    (
        "a decided item claims its dependent certificates were re-issued",
        "verification.py",
        ('view["dependents_reissued"] = False', 'view["dependents_reissued"] = True'),
        ["tests/test_verification_decisions.py"],
    ),
    (
        "an engine limit is filed as a question for an expert who cannot close it",
        "verification.py",
        ('    if not item.get("author_can_close", True):', "    if False:"),
        ["tests/test_verification_issue.py"],
    ),
    (
        "repeated fruitless claims never take an entry out of the offered pool",
        "catalog.py",
        ("        return len(self.attempts_without_progress()) >= after", "        return False"),
        ["tests/test_catalog_parking.py"],
    ),
    (
        "progress does not clear the run of fruitless claims, so an entry parks despite moving",
        "catalog.py",
        ("            if attempt.progress_marker != marker:\n                break",
         "            if False:\n                break"),
        ["tests/test_catalog_parking.py"],
    ),
    (
        "the attempt record is not persisted, so the retry bound resets on every restart",
        "catalog.py",
        ('            **({"outcome": self.outcome} if self.outcome else {}),\n', ""),
        ["tests/test_catalog_parking.py"],
    ),
    (
        "only the majority reason is reported, hiding the claimant who found something different",
        "catalog.py",
        ("                for reason, count in sorted(said.items(), key=lambda kv: (-kv[1], kv[0]))",
         "                for reason, count in [said.most_common(1)[0]]"),
        ["tests/test_catalog_parking.py"],
    ),
    (
        "a saved attempt the retry bound could never compare against the record is accepted",
        "catalog.py",
        ("        if not 0 <= attempt.progress_marker <= len(history):", "        if False:"),
        ["tests/test_catalog_parking.py"],
    ),
    (
        "the stop reason names the first cause that holds rather than every one",
        "query.py",
        ("            if parked:\n                causes.append(",
         "            if parked and not causes:\n                causes.append("),
        ["tests/test_loop_status.py"],
    ),
    (
        "a superseded certificate is counted among what the repository has published",
        "query.py",
        ("                            if self.superseded_by(digest) is None",
         "                            if True"),
        ["tests/test_loop_status.py"],
    ),
    # --- reconciling the queue with its issues, 2026-09-06 -------------------------------------
    (
        "a relabelled issue disappears from the report by having drifted",
        "verification.py",
        ("if ISSUE_LABEL not in labels and fingerprint not in known:",
         "if ISSUE_LABEL not in labels:"),
        ["tests/test_issue_reconciliation.py"],
    ),
    (
        "an issue is matched on a certificate digest somebody quoted rather than on its question",
        "verification.py",
        ("        fingerprint = next(\n            (candidate for candidate in candidates if candidate in known),\n            candidates[0] if candidates else None,\n        )",
         "        fingerprint = candidates[0] if candidates else None"),
        ["tests/test_issue_reconciliation.py"],
    ),
    (
        "a fetch that left out the field the match depends on reads as every issue having drifted",
        "verification.py",
        ('for field in ("number", "state", "body"):', "for field in ():"),
        ["tests/test_issue_reconciliation.py"],
    ),
    (
        "two open issues asking one question are reported as two issues in sync",
        "verification.py",
        ('        if len(numbers) > 1 and record["state"] == "OPEN":', "        if False:"),
        ["tests/test_issue_reconciliation.py"],
    ),
    (
        "an issue closed while its question is still pending reads as in sync",
        "verification.py",
        ('            if state != "OPEN":', "            if False:"),
        ["tests/test_issue_reconciliation.py"],
    ),
    # --- what a repository owes a re-run, 2026-09-06 -------------------------------------------
    (
        "a confirmation is presented as a re-certification the repository owes",
        "verification.py",
        ('            if decision["kind"] == "confirm":', "            if False:"),
        ["tests/test_recertification_due.py"],
    ),
    (
        "the dependents of a rejected estimate are listed as re-runnable",
        "verification.py",
        ('                if decision["kind"] == "correct":', "                if True:"),
        ["tests/test_recertification_due.py"],
    ),
    (
        "a certificate naming an older revision of the judging code reads as fresh",
        "verification.py",
        ('        if algorithm is None or f"rev {revision}" not in algorithm:',
         "        if False:"),
        ["tests/test_recertification_due.py"],
    ),
    (
        "a class the freshness check cannot name passes it instead of being unchecked",
        "verification.py",
        ("        if revision is None:\n            unknown_class.append(",
         "        if revision is None:\n            [].append("),
        ["tests/test_recertification_due.py"],
    ),
    # --- the Turing wavelength claim, 2026-09-06 -----------------------------------------------
    (
        "a wavelength read while the pattern is still forming is published as the one it selects",
        "spatial.py",
        ("    if settled != dominant:", "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a domain that cannot tell two wavelengths apart is run anyway, then judged",
        "spatial.py",
        ("    if predicted_resolution > tolerance.reproduced_within:", "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a run that settled on a mode coarser than the domain was cleared for is judged",
        "spatial.py",
        ("    if resolution > tolerance.reproduced_within:", "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "the seed's own modes are reported as a pattern the model selected",
        "spatial.py",
        ("    if amplitudes[dominant] <= 10.0 * seeded:", "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a reaction unstable without diffusion is certified as a Turing pattern",
        "spatial.py",
        ("    if trace >= 0.0 or det <= 0.0:", "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a reaction family this class does not implement is run as a neighbouring one",
        "spatial.py",
        ("        if self.kinetics not in TURING_KINETICS:", "        if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a pattern claim publishes a clean pass for modes the engine's own wall decided",
        "spatial.py",
        ("        if assessment.assumption_qualified\n    )", "        if False\n    )"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    # --- the wall a pattern is measured on, 2026-09-06 ------------------------------------------
    (
        "a periodic pattern claim is measured on the zero-flux mode set",
        "spatial.py",
        ('        return self.length / self.points if self.wall == "periodic" else self.length / (self.points - 1)',
         "        return self.length / (self.points - 1)"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a periodic pattern that drifted a quarter wavelength is reported as absent",
        "spatial.py",
        ('    if wall == "periodic":', "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    (
        "a two-species run accepts a wall it cannot hold a value for",
        "spatial.py",
        ('    if boundary not in ("no-flux", "periodic"):', "    if False:"),
        ["tests/test_spatial_pattern_claim.py"],
    ),
    # --- the update scheme, carried to the run and to the certificate, 2026-09-06 ---------------
    (
        "a steady-state verdict is qualified for a scheme that cannot move it",
        "logical.py",
        ("    if claim.attractors is None:\n        # The claim is judged on a *fixed point*",
         "    if False:\n        # The claim is judged on a *fixed point*"),
        ["tests/test_logical_scheme.py"],
    ),
    (
        "a reported attractor set is judged as if it were a single steady state",
        "logical.py",
        ("    if claim.attractors is not None:\n        return judge_attractor_set(",
         "    if False:\n        return judge_attractor_set("),
        ["tests/test_logical_scheme.py"],
    ),
    (
        "a certificate announces one update scheme over verdicts computed under the other",
        "logical.py",
        ('    if f"{scheme.value}-update" not in algorithm:', "    if False:"),
        ["tests/test_logical_scheme.py"],
    ),
    (
        "claims judged under two schemes share one pin, which can name only one",
        "logical.py",
        ("    if len(wanted) > 1:", "    if False:"),
        ["tests/test_logical_scheme.py"],
    ),
    (
        "an unstated scheme that changes the attractors is not qualified for",
        "logical.py",
        ('    if sensitivity is None or sensitivity.get("agree"):', "    if True:"),
        ["tests/test_logical_scheme.py"],
    ),
    # --- a class can be partly corroborated, 2026-09-06 -----------------------------------------
    (
        "a class re-run on fewer certificates than it published reads as fully corroborated",
        "query.py",
        ("        if published is not None and model_class in published:", "        if False:"),
        ["tests/test_corroboration_surface.py"],
    ),
    (
        "a class re-running each claim counts its claims as if they were certificates",
        "query.py",
        ('            covered = len({key.split(":", 1)[0] for key in record})',
         "            covered = len(record)"),
        ["tests/test_corroboration_surface.py"],
    ),
    (
        "a scalar corroboration reports agreement whatever the two engines returned",
        "corroboration.py",
        ("        distance=0.0 if scale == 0.0 else abs(mine - theirs) / scale,",
         "        distance=0.0,"),
        ["tests/test_spatial_corroboration.py"],
    ),
    (
        "a discrete mode match is published on the curve classes' distance scale",
        "corroboration.py",
        ('        versions=(_reprolith_build(pin), _scipy_version()),\n        comparison="exact-match",\n    )',
         "        versions=(_reprolith_build(pin), _scipy_version()),\n    )"),
        ["tests/test_spatial_corroboration.py"],
    ),
    (
        "a claim this class abstains on is corroborated against a number it never produced",
        "corroboration.py",
        ("    if mine.wavelength is None:", "    if False:"),
        ["tests/test_spatial_corroboration.py"],
    ),
    (
        "a front certificate reports its settling drift and hides what its time step costs",
        "spatial.py",
        ("            + _front_step_cost(moved)", "            + \"\""),
        ["tests/test_spatial_front_claim.py"],
    ),
    (
        "an unreadable step sensitivity is published as costing nothing",
        "spatial.py",
        ("    if coarse is None or fine is None or coarse == 0.0:\n        return None",
         "    if coarse is None or fine is None or coarse == 0.0:\n        return 0.0"),
        ["tests/test_spatial_front_claim.py"],
    ),
    (
        "a front speed the time step could carry across its line is published anyway",
        "spatial.py",
        ("    if moved is not None and (moved > tolerance.reproduced_within or moved > nearest):",
         "    if False:"),
        ["tests/test_spatial_front_claim.py"],
    ),
    (
        "a published grid-dependent metric hides what its sampling cost it",
        "certify.py",
        ("    if grid_change is not None:", "    if False:"),
        ["tests/test_auc_convergence.py"],
    ),
    (
        "a lethal knockout the other implementation declines to answer for is read as zero growth",
        "corroboration.py",
        ('            if str(status) != "infeasible":', "            if False:"),
        ["tests/test_frog_publication.py"],
    ),
    (
        "two fingerprints of different models are compared on the part that lines up",
        "corroboration.py",
        ('    if missing:\n        raise ValueError(\n            "these fingerprints do not describe the same model: "',
         '    if False:\n        raise ValueError(\n            "these fingerprints do not describe the same model: "'),
        ["tests/test_frog_publication.py"],
    ),
]


def main() -> int:
    survivors: list[str] = []
    stale: list[str] = []
    ambiguous: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for meaning, module, (anchor, replacement), tests in MUTATIONS:
            package = Path(scratch) / "python"
            shutil.rmtree(package, ignore_errors=True)
            shutil.copytree(REPO / "python", package)
            target = package / "reprolith" / module
            source = target.read_text(encoding="utf-8")
            found = source.count(anchor)
            if found == 0:
                stale.append(f"{module}: {meaning}")
                print(f"STALE     {meaning}")
                continue
            if found > 1:
                # `str.replace(anchor, repl, 1)` mutates the *first* match, so an anchor that
                # appears twice silently mutates whichever site comes first — and the entry that
                # owns the other one stops being checked at all. That happened on 2026-09-07:
                # `if missing:\n        raise ValueError(` was written for the SAT check and a new
                # function further up the same module came to contain it, so a guard reported
                # SURVIVED while another entry "passed" by mutating code its tests never cover.
                # A quote that is not unique is a guard pointed at the wrong text, which this
                # repository already refuses in its loop-note citations.
                ambiguous.append(f"{module}: {meaning} ({found} matches)")
                print(f"AMBIGUOUS {meaning} — the anchor matches {found} places")
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

    if ambiguous:
        print(f"\n{len(ambiguous)} anchor(s) match more than one place, so the entry that owns the")
        print("other site is not being checked at all. Make each anchor unique — include the line")
        print("under it, or the message it raises.")
        for entry in ambiguous:
            print(f"  - {entry}")
    if stale:
        print(f"\n{len(stale)} mutation(s) no longer apply — the code moved and this list did not.")
        print("Update the anchor or delete the entry; a checker that quietly checks less is the")
        print("defect it exists to catch.")
    if survivors:
        print(f"\n{len(survivors)} guard(s) can be removed with every test still passing:")
        for meaning in survivors:
            print(f"  - {meaning}")
    if not stale and not survivors and not ambiguous:
        print(f"\nall {len(MUTATIONS)} guards are held by a test that fails without them")
    return 1 if (stale or survivors or ambiguous) else 0


if __name__ == "__main__":
    raise SystemExit(main())
