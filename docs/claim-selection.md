# Choosing which claims to reproduce

A paper's thirty-three published numbers are not thirty-three independent things to check. Ten
tissues at three doses is one model shown thirty-three ways, and reproducing plasma at 500, 1000
and 1500 mg exercises the same absorption and elimination machinery three times while leaving the
rest of the model untouched. If you can afford to reproduce four results, which four?

`reprolith select-claims <accession> --budget <n>` answers that, and it is a **plan, not a
verdict**. No model is run, nothing is certified, and a claim left unselected is *unattempted* —
neither reproduced nor unreproduced. Which of a paper's results matter is the reader's judgment,
and this never pretends otherwise.

```
$ reprolith select-claims BIOMD0000001028 --budget 3
SELECTED 3 OF 33 TARGETABLE CLAIMS
  Cmax-1000mg
  Cmax-red-blood-cells-1000mg
  Cmax-stomach-1000mg
  independent evidential value: 2.733 (gross 3 less 0.2666 overlap)
  spends 3 of a 3 budget
  witnesses 54 distinct model element(s)
  ranking one at a time would have taken: Cmax-1000mg, Cmax-250mg-Chung, Cmax-500mg
  and scored 0 over 46 distinct model element(s)
```

The baseline line is the point. Reading down a ranking one claim at a time takes plasma at three
doses — three views of one fit, scoring **0** once their overlap is charged, and witnessing 46
model elements. Choosing as a *set* takes three different tissues, scores 2.733, and witnesses 54.
Same budget, same candidates, same objective.

The greedy ranking is reported beside the answer on purpose. A selection is a decision about what
evidence a certificate will and will not rest on, so what it *changed* is part of the finding:
where the two agree there was no set-level structure to exploit, and where they differ you can see
what the ranking would have bought instead.

## What a claim rests on, and where that number comes from

The whole thing turns on each claim's **footprint** — the model elements its value is computed
from. That is what two claims can share, and so the only thing that makes a set of them more or
less independent evidence than the sum of its members.

A footprint is **derived from the model**, never from the claim's own prose. An SBML model states,
in machine-readable form, which symbols each quantity is computed from: its reactions' rate laws,
its assignment and rate rules, its initial assignments, the compartment a species sits in, and the
function definitions those call. Walking that graph is reading the model. Matching parameter names
out of a claim's description would invent a dependency and then let a selection be defended by it,
which the `claim-selection` spec refuses on purpose.

Two decisions in that walk were measured rather than chosen, and both are in
`tests/test_footprints.py`.

**The transitive closure is the obvious answer and it is useless.** A PBPK model is strongly
connected — plasma feeds every tissue and every tissue feeds plasma — so the closure from any
species is the whole model. All 80 of this corpus's claims came back with an identical 116-element
footprint. Identical footprints overlap completely, so a selection over them reports that
reproducing any one claim makes every other worthless: a statement about the walk, not about the
paper. Mean pairwise overlap across one paper's ten tissues at three doses:

| walk | mean pairwise Jaccard overlap |
| --- | --- |
| depth 1 | 0.01 |
| **depth 2 (the default)** | **0.20** |
| depth 3 | 0.37 |
| transitive closure | 1.00 |

Depth 2 is where a claim has reached its own machinery — its tissue's partition coefficient, that
tissue's blood flow, the two reactions moving drug in and out of it, and the arterial pool and flow
function every tissue routes through — and not yet the whole model. Depth 1 stops before the shared
machinery and reports every claim as independent.

**A target the walk cannot get beyond is empty, never `{itself}`.** An empty footprint is what
selection reads as *not characterized*; a singleton is a characterized claim that overlaps nothing,
so thirty-three views of one model each carrying only their own name would publish as thirty-three
independent pieces of evidence. This is not hypothetical: walking the *dossier's* own recorded
equations rather than the model file produced exactly that for 77 of the 80 claims, because these
models' dynamics are 33 reactions that `ingest_sbml` declines to carry and records as a gap. That
is why the derivation reads the model file.

## What it says when it cannot do the job

Every report carries a `limits` field, and for most of this capability's life it was the whole
answer. A selection over claims with no recorded footprint has no overlap to measure, so its answer
*is* the ranking's — and saying so is the difference between an honest report and one claiming an
analysis it did not perform.

It also names **footprint elements this dossier records nothing for**. A footprint element derived
from the model can legitimately be something the dossier does not carry: on these papers, the
reaction ids, because the dossier records the 33-reaction network as a gap rather than
misrepresenting it. Those are reported, never refused — an unanchored name is one nothing in the
dossier can corroborate, so a reader can tell a footprint anchored in recorded structure from one
that is a bare assertion. Restricting footprints to the dossier's own vocabulary was measured and
rejected: it changes mean overlap from 0.195 to 0.175, so it costs nothing in discrimination, and
it would make every footprint *look* anchored while the dossier still cannot corroborate the
reactions.

## What it reaches today

Four papers — the metformin entries, which are the only ones in this repository with dossiers at
all. The other five model classes ship certificates and agreement reports but no dossiers, so
there is nothing for a selection to read there. That is a gap in what has been ingested, not in
this capability, and `select-claims` on an accession with no dossier says so rather than returning
an empty plan.

## Over MCP

The `select_claims` tool takes `accession` and `budget` and returns the same object the terminal
prints, `limits` included. See [mcp-server.md](mcp-server.md).
