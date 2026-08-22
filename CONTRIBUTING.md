# Contributing to Reprolith

Reprolith reproduces published biomedical models and certifies whether they reproduce their own
results. It gets better in two ways, and **both need people who know the science**:

1. **Validate its judgment.** When Reprolith is not confident about a load-bearing value — a
   shaky extraction, an assumption it had to make, a verdict near its tolerance — it records its
   best estimate and marks the result as resting on it. Confirming, correcting, or rejecting those
   values is the single most valuable thing an expert can do here. **Today you open that
   verification issue by hand** using the template: Reprolith's queue exists as a library
   (`reprolith.VerificationQueue`) but nothing wires it to GitHub yet, so nothing is filed
   automatically. Every certificate's gap report and assumption list is where to look for what
   needs checking — `reprolith gaps <digest>` prints it.
2. **Grow and correct the catalog.** Propose a paper to reproduce, add a ground-truth
   reproducibility label, or fix a mis-extraction — as a pull request.

You do **not** need to understand Reprolith's internals to help. Every verification issue is
self-contained: the question, the source context, Reprolith's best guess and reasoning, and what
depends on it. If you know the modeling, you can decide.

## How the collaboration works

- **Verification issues** are Reprolith's questions to you. Answer in the issue: confirm,
  correct (with the right value and a source), or reject (with why). Your decision, your name,
  and your rationale become the record. Re-verification of what depended on a corrected value is
  the intent (`reprolith.reverify_dependents` implements it), but it is not automated yet — a
  merged correction triggers nothing on its own today.
- **Pull requests** are how any change to the data or code lands. Reference the issue a PR
  resolves. The same automated gates run on every PR, whether it comes from a human or from
  Reprolith's own build loop — nobody gets a lower bar.
- **Certificates stay honest.** A result that only reproduced because of an assumption, or that
  rests on a value still awaiting your confirmation, is reported as *qualified* — never as a clean
  reproduction. Please help us keep it that way.

## The gates every change must pass

CI runs all of these on every pull request, from a human or from Reprolith's own build loop:

- `openspec validate --specs --strict` — the specs stay consistent.
- `ruff check` — lint.
- `mypy` — types.
- `pytest` — tests, including the honesty invariants (determinism, inescapable scope,
  assumption-qualification) and the discipline-loop record.

The last one catches people out, so it is worth naming: adding a failure mode, adding a default
tolerance, or producing a blind verdict that disagrees with its ground-truth label all require a
written note in [`datasets/loop_notes.json`](datasets/loop_notes.json) saying what put it there,
with at least one citation quoting the words it is cited for. `tests/test_loop_notes.py` fails
until there is one. See [`docs/discipline-loop.md`](docs/discipline-loop.md).

Run them locally before opening a PR:

```bash
pip install -e ".[dev]"
ruff check .
mypy
pytest -q
```

(Spec validation uses the OpenSpec CLI: `npx @fission-ai/openspec validate --specs --strict`.)

## If you add a guard, measure it

A guard is a claim about what cannot happen, and it is worth exactly what its measurement is worth.
Four consecutive audit rounds over this repo found 26, 17, 12 and 12 defects — and every round after
the first found them *in the previous round's fixes*, all of them invisible to the gates above. So
when you add a check, a refusal, or a stability rule:

- **Measure the thing it refuses.** Show the number it was wrong by before, and after. A guard
  justified by reasoning rather than by a run is the shape that keeps failing here.
- **Write a test that fails when the fix is removed.** Revert your own change and watch it go red.
  Four guards shipped in one batch had no test at all, and the suite stayed green without them.
- **Apply the rule to every path, including the ones you are adding in the same commit.** The
  sharpest failure in this history is a guard whose own new branch broke the invariant stated in
  its docstring three lines above.
- **Prefer one function called from every layer** over one check per layer. A rule enforced in the
  builder, the load path, and a class front-end separately ended up with three implementations and
  two answers about the same certificate.
- **A guard that is too strict is a defect too.** A stability limit tightened to a safe-looking
  constant broke a validated Turing dispersion relation; the measured answer was different from the
  cautious one.
- **Cover the case the rule is about, not one point inside it.** A whole round's findings were a
  correct rule applied to every case but one, and the omitted case was the one that mattered most:
  a flat-reference fallback that tested `span == 0.0`, and so relieved only the references that
  never occur while missing every nearly-flat one; a resolvability check that returned early on a
  reported mean of zero, the value it should be strictest at; an override guard covering rules and
  initial assignments but not event assignments; a revision pin spanning four of the five modules
  that decide the number. Enumerate the cases the rule is written for, then check the code against
  that list.
- **Ask which direction the fix errs in, not just whether it is safe.** A repair verified
  one-directional over 200,000 inputs was still wrong, because the direction it moved in — widening
  a denominator — is the one that turns a miss into a pass. The same round set a badge colour for
  the case it was written for and applied it to all four verdicts, upgrading two. "It can only do X"
  is an argument only once you have said whether X is the harmful direction.
- **A number is only as good as what it is attributed to.** The corpus's first independent audit
  found every reference value reproducible — and one of them credited to a paper reporting a
  different number, because the reference network has a node the paper's does not. Check that the
  source you cite reports the thing you cite it for, not merely that your number is right.
- **An accessor has a version, and so does the file.** A guard that read a Level 3 accessor saw
  nothing on Level 2, which is most of the curated corpus — it covered 10 of 234 cases while its
  comment claimed all of them. When you read a model through a library, check the attribute exists
  at the level the files you actually ingest are written in.
- **If a tool tells you it failed, read it.** The pinned engine reports an abandoned time course by
  returning `False` and recording the samples it reached — all finite, so the non-finite guard
  cannot see it. That return value was discarded and the sample count never compared to the one
  requested, so a run that stopped at t = 5 of 100 was judged as if it had finished, at relative
  error 0.0000. Validate what came back, not only what went in.

[`docs/findings-note.md`](docs/findings-note.md) records what each round found, with the numbers.

## Extending a self-validation set

The constraint-based and generic-kinetic classes validate Reprolith non-circularly against an
**independent** tool: COBRApy for FBA growth/essentiality/variability, libRoadRunner for kinetic
time-courses. To add a curated model to a set:

1. Add its file under `datasets/constraint_based/cross_validation/` or `datasets/kinetic/`
   (with its entry in the manifest, for the kinetic set).
2. Regenerate the committed reference values from the independent tool:
   ```bash
   pip install -e ".[refgen]"
   python scripts/regenerate_fba_references.py       # or regenerate_kinetic_references.py
   ```
3. Run the tests — they read the committed references and need only `.[engine,fba]`, not the
   reference generators. The milestone scripts (`scripts/run_*_milestone.py`) fold the new model
   into the blind agreement run automatically.

The reference must come from a tool that shares no implementation with Reprolith's engine, so the
check stays non-circular. Never hand-write a reference value.

## The one rule we will not bend

**Reproducible is not correct, and neither is clinically valid.** Reprolith certifies only that a
model regenerates its own published results. No contribution may weaken a certificate's scope
statement, its assumption-qualification, or its blind self-validation. These are enforced in code
and in CI, and a change that erodes them fails the gates by design.

## Ways to start

- Answer an open **verification issue** (opened from the `verification` issue template).
- Open a **candidate paper** issue to nominate a model worth reproducing.
- Pick up a task from `openspec/changes/` or an item from
  `openspec/initiatives/catalog-backlog/roadmap.md`.

Thank you for helping make a literature that should be runnable, actually runnable.
