# Before you submit: what a reproducer will find

You have a model, a simulation document, and a paper. Someone will eventually try to re-run your
work from those files. This is the check that tells you what they will hit, before a reviewer does
— it runs no model, reaches no verdict, and issues no certificate.

```bash
pip install reprolith
reprolith claims-template --model paper.xml --sedml paper.sedml --out my_claims.json
reprolith archive-check paper.omex --claims my_claims.json
reprolith archive-check --sedml paper.sedml --model paper.xml --claims my_claims.json
reprolith params-check --model paper.xml --parameters my_parameters.json
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
| **Will it run at all?** | A reaction with no `kineticLaw`, or one whose `math` is empty, states no rate. No engine tells you so. COPASI imports the file, starts the run and abandons it partway, returning a short trajectory rather than an error; libRoadRunner refuses an empty `math` with a message about compiler AST nodes, and integrates an *absent* law with that reaction's rate taken as zero — a complete, plausible curve with everything downstream of it sitting at 0.0, nothing printed. This leads the fix list, because everything below it assumes there is a run to check. Not asked of a constraint-based or logical model, which has no rate laws by construction. |
| **Can they open it?** | A zip with no manifest, a manifest listing files that are not there, several experiments with none marked master, an experiment running more than one model. Each refusal names the ambiguity; a file that cannot be read is the whole report. |
| **Do your two files agree?** | An override aimed at a parameter the model does not have overrides nothing, so the run silently reproduces the *unmodified* model and looks fine. Every target is resolved by its nesting in the model, so an override aimed at the right name inside the wrong parent is caught. |
| **Does it say what you published?** | A document whose outputs are all `report`s states no published result: it can be run, but there is nothing to check it against. A `plot` is your own statement that a curve is a shown result. |
| **Can they adopt your run verbatim?** | A parameter scan, a model the document modifies, or a window that does not start at zero all mean a reproducer must reconstruct the run rather than read it. |
| **Does your model carry the values you published?** | Only `params-check`, and only for the parameters you pair up. Your paper's parameter table says `Kt:p` for liver is 5.5; your deposit says whatever it says. Every reproduction in this repository would pass a model whose inputs differ from its paper, because reproductions check outputs. |
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

## The parameters file

`params-check` reads a JSON file pairing each model parameter id with the value your paper reports
for it:

```json
{"parameters": [
  {"parameter": "Ktp_Liver", "reported": 5.5, "source_location": "Table 3, Liver row"}
]}
```

The pairing is yours to make and is never inferred. "Lungs" is `Ktp_Lung` and "Intestine" is
`Ktp_IntestineVascular`, and no rule would produce either — a check that guessed would report a
mismatch against a parameter you never meant.

Two things it will not do. It compares **at the precision your paper printed**: a table printing
`0.7` against a model carrying `0.73` agrees, because the table cannot tell `0.73` from `0.749`,
and demanding equality would accuse a correct deposit. And it never compares a value an
`initialAssignment` or a rule overrides — the number in that `value` attribute is not what runs, so
agreement with it would be the most confident wrong answer available. Those are reported as *not
compared*, separately from a mismatch, and they do not fail the command.

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

## When a fix list says your paper is wrong

Reprolith can conclude that the number your table reports is the thing that does not fit, rather
than your model. When it does, the fix list says so in as many words, and says it as a hypothesis:

```
fix: check Table 7's Brain Cmax, which equals plasma's while its AUC24 and Cmean are 0.80 of
     plasma's — Reprolith's hypothesis is that the reported value is wrong rather than the
     model, so confirm it against your own run before changing anything
```

The other direction reads differently on purpose, so that naming the fault is worth something:

```
fix: reconcile the model with what your paper reports: the four dose events the model carries,
     against the eight its own name states. Reprolith's hypothesis is that the shipped model,
     not the reported value, is what falls short
```

A fault is always a hypothesis and never a proven cause. What it rests on is in the line above it
— the measured discrepancy — and in the element it names, which is chosen so you can check the
claim yourself without re-running anything.

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

The section headed "what a reproducer would have to read off your figures" is advice, not a
finding. If your document plots curves and ships no values behind them — which is what almost every
archive does, because publishing results as figures is what papers do — it lists them, says what it
costs (nobody can check those curves without first digitizing your figure, and a digitized
reference is judged in a band twice as wide as a number you print), and names the cheap way out:
ship the series as a data file your document points at, with a `dataDescription` selecting one
column per curve. You have those numbers; the reproducer does not. It never holds up your
submission, because a document doing exactly what SED-ML is for is not a defect.

If you would rather see what that reading costs before deciding, [`figure-values.md`](figure-values.md)
is the other side of it: what a curator's digitization of your figure carries, and the measurement
of what a *flawless* one still spends — a five-point reading of a PK-shaped curve misses the curve
it was read off by more than the whole tolerance, with no model involved. That is the number behind
"a band twice as wide", and it is the argument for shipping the series.

And the separate list headed "what Reprolith's own extraction would not carry" is **not** a fix
list. Some of it your archive genuinely omits; some of it your archive states perfectly well and
Reprolith cannot represent. Nothing distinguishes the two, so nothing there is asked of you and
none of it decides readiness.

The same fact follows you past the check. If a claim of yours is eventually certified against a
curator's reading of your figure, the pre-submission report on that certificate names it, states
what it cost — against a reading rather than a number, in the wider band that carries, stated as
the multiplier that claim's own comparison uses rather than one number for all three — and repeats
the cheap way out. It is printed even above a READY TO SUBMIT, and for the same reason it is not a fix here:
both things are true at once, and only one of them is yours to change.

## After it is green

A green check means a reproducer can read your files and knows what to check — not that your model
is right, and not that it is safe to use on anyone. If you want the verdict itself, submit the
model and get a [certificate](../README.md): per claim, reproduced or not, with the reason, and the
scope statement that says what it does and does not mean.
