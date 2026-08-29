# Before you submit: what a reproducer will find

You have a model, a simulation document, and a paper. Someone will eventually try to re-run your
work from those files. This is the check that tells you what they will hit, before a reviewer does
— it runs no model, reaches no verdict, and issues no certificate.

```bash
pip install reprolith
reprolith claims-template --model paper.xml --sedml paper.sedml --out my_claims.json
reprolith archive-check paper.omex --claims my_claims.json
reprolith archive-check --sedml paper.sedml --model paper.xml --claims my_claims.json
```

The first line writes the claims file the other two read; see [the claims file](#the-claims-file).
It is the only step that needs anything from you, and it needs two things per published result.

Both forms answer the same question. Use the second if your files are loose, which most papers'
are: they are packaged into the archive they describe and that archive is checked. The exit status
is the answer — `0` when a reproducer can read your files and knows what to check, non-zero
otherwise — so it drops into a pre-submission hook or a CI job.

## What it checks

| | What a reproducer would hit |
| --- | --- |
| **Can they open it?** | A zip with no manifest, a manifest listing files that are not there, several experiments with none marked master, an experiment running more than one model. Each refusal names the ambiguity; a file that cannot be read is the whole report. |
| **Do your two files agree?** | An override aimed at a parameter the model does not have overrides nothing, so the run silently reproduces the *unmodified* model and looks fine. Every target is resolved by its nesting in the model, so an override aimed at the right name inside the wrong parent is caught. |
| **Does it say what you published?** | A document whose outputs are all `report`s states no published result: it can be run, but there is nothing to check it against. A `plot` is your own statement that a curve is a shown result. |
| **Can they adopt your run verbatim?** | A parameter scan, a model the document modifies, or a window that does not start at zero all mean a reproducer must reconstruct the run rather than read it. |
| **Does it run what your paper reports?** | Only with `--claims`. See below — this is the one nothing in your archive can answer, and the one that fails most quietly. |

## The claims file

Nothing in an archive knows what your paper says. You do. `--claims` takes a JSON file of the
results your paper reports.

**You do not have to write it from scratch.** `claims-template` writes it out of the files you
already have, with everything derivable filled in:

```bash
reprolith claims-template --model paper.xml --sedml paper.sedml --out my_claims.json
reprolith claims-template paper.omex --out my_claims.json
```

One stub per curve your document plots — because a plot is your own statement that a curve is a
shown result — each naming the model output it reads. Delete the ones your paper does not report,
fill in `reported` and `source_location` on what is left, and pass the file back to
`archive-check`. It never writes a `reported` value: a template that read one off your model would
hand the check your model's own output as your paper's claim, and the comparison would pass by
construction, which is the exact failure the check exists to catch.

Without `--sedml` it writes no stubs at all — a model states what *can* be read and never what
your paper showed — but it still lists both things you need to write them by hand: every output a
claim can read, and every parameter a claim can set. A parameter your model's own math determines
is listed apart, under `model_determines`, because an override aimed at one is refused later.

The fields, whether you write them or edit them:

```json
{
  "claims": [
    {
      "claim_id": "Cmax-1000mg",
      "quantity": "plasma Cmax after 1000 mg single oral dose",
      "species": "mPlasmaVenous",
      "reported": 11.2,
      "source_location": "Table 4",
      "metric": "cmax",
      "parameter_overrides": {"Metformin_Dose_in_Lumen_in_mg": 779.9}
    }
  ]
}
```

| Field | What it is |
| --- | --- |
| `claim_id` | your own name for the result |
| `quantity` | what the paper reports, in words |
| `species` | the model element the value is read from |
| `reported` | the number your paper prints |
| `source_location` | where in the paper it is — the table, the figure panel |
| `metric` | how the number comes off the trajectory: `cmax`, `auc`, or `final` |
| `parameter_overrides` | the values that claim holds at — the dose, the condition |
| `schedule` | when the arm begins from an earlier dose: a list of `{"duration": …, "parameter_overrides": {…}}` segments run in order, the last one being the arm you report |

If your result is reported for an arm that follows an earlier administration — a pre-dose the
evening before, a loading dose — `schedule` is how to say so. Each segment runs your model with its
own values, starting from where the previous segment ended, so your own dosing machinery gives
every dose and nothing is added to your model. Use `schedule` **or** `parameter_overrides`, not
both: the overrides are the one-segment spelling of the same thing.

A bare list of those records works too, as does a file holding several papers under `entries`
keyed by accession — the shape [`datasets/pkpd_claims.json`](../datasets/pkpd_claims.json) uses —
with `--accession` to pick one.

`parameter_overrides` is the field that earns the check. On the metformin PBPK model's own shipped
files, the paper's 1000 mg dose is 779.9 mg of free base in the model's units, and the document
scans the dose over 389.2, 778.4 and 1167.6 mg:

```
FIX BEFORE YOU SUBMIT (most impactful first)
  - the manuscript's claim 'Cmax-1000mg' sets 'Metformin_Dose_in_Lumen_in_mg' to 779.9, which the
    archive never runs: the model states 389.92 and the experiment runs it at 389.2, 778.4, 1167.6
      fix: ship a run that produces the result your paper reports; a document that runs a
           neighbouring arm reproduces a plausible number and flags nothing
```

Every file validates. The run completes. The number is close. That is the failure this exists for.

## Starting from your paper instead of your model

`claims-template` starts from the model and leaves the number blank. If you would rather start
from the paper, `claims-propose` reads the tables it prints:

```bash
reprolith claims-propose --tables my_tables.json --out candidates.json
```

Every number a table prints on its own in a cell becomes a candidate, with the row and column that
name it as its source location, and a `metric` where the column heading states one (`Cmax`, `AUC`).
Delete the ones your model is not asked to reproduce — a table carries measured values, fitted
values, percentage differences and doses side by side — and name the model output each survivor
reads.

It never proposes the model output. Matching a table's "Plasma" to your `mPlasmaVenous` is a
judgment, and a wrong match checks a real number against the wrong species, which is worse than no
candidate at all. It also refuses a table whose rows are not all the width of its header: a cell
spanning rows is written once, and reading the rest positionally puts a value under the wrong
column.

## Checking your claims against your own paper

The claims file says what your paper reports. Nothing checked that it does — and in this
repository's own corpus, one of exactly two manuscript-read reference values turned out to be a
number the paper does not contain. It passed every check for months, because it was inside
tolerance.

```bash
reprolith claims-check --claims my_claims.json --tables my_tables.json
```

`--tables` is the rows of the tables your paper prints, as JSON — `{"Table 6": {"rows": [[...]]}}`,
or the shape [`datasets/manuscripts/`](../datasets/manuscripts/) uses. For each claim it asks one
mechanical question: **is the number you state printed in the table you cite?** It exits non-zero
only when the answer is no.

It will not tell you *which* cell is the right one — that is your judgment, and a check that
guessed would accuse correct claims. A claim citing a figure panel or a sentence, or a table you
did not supply, is reported as **not checked**, never as wrong, and never fails the command: an
absence of evidence is not evidence of absence.

## What it will not tell you

It is built to under-report rather than accuse a correct archive, so a comparison it cannot make
mechanically is one it does not make:

- **The run window.** Your claim says 24 hours; a uniform time course says `outputEndTime="30"` and
  no unit at all.
- **Outputs no claim covers.** A document routinely records more columns than a paper shows, and
  the claims file you wrote is yours — the difference is more often a gap in it than in your files.
- **An id two model elements carry**, a target it cannot resolve, a scan whose values are not
  listed, a change whose effect it would have to compute, or a parameter your model's own math
  determines. Failing to read something is not evidence that it disagrees.
- **Your manifest, when you have no archive.** The loose-file form generates one; it says so.
- **Whether a constraint-based, logical, spatial or multi-component model states its published
  results.** Those questions are time-course questions — a model declaring the SBML `fbc` package
  is solved at steady state, a `qual` one advances in discrete update steps — so they are withheld
  and named under "what this check did not judge", rather than answered with advice about a run
  nobody performs. What still applies (can they open it, do your two files agree, does it run the
  values your paper reports) is still checked. Such a model is never reported ready, because
  "ready" would claim a reproducer knows what to check, which nothing here established.

And the separate list headed "what Reprolith's own extraction would not carry" is **not** a fix
list. Some of it your archive genuinely omits; some of it your archive states perfectly well and
Reprolith cannot represent. Nothing distinguishes the two, so nothing there is asked of you and
none of it decides readiness.

## After it is green

A green check means a reproducer can read your files and knows what to check — not that your model
is right, and not that it is safe to use on anyone. If you want the verdict itself, submit the
model and get a [certificate](../README.md): per claim, reproduced or not, with the reason, and the
scope statement that says what it does and does not mean.
