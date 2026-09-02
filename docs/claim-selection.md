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

## Where each footprint came from

A derived footprint and a curator's footprint are not the same evidence, and once written down
they look identical. The first is re-derivable — anyone with the model file gets the same set. The
second is an assertion about the model that the model was never asked to confirm: often better
informed than the walk, and not checkable by re-running anything. Since a selection defends itself
with the *overlap between footprints*, a reader weighing what a budget skipped has to know which
they are looking at.

So every footprint states its origin, and one that does not is refused — where a dossier is built
and where it is loaded, because a hand-edited or contributed dossier arrives through the loader.
The count travels in every report and both surfaces print it:

```
  footprints: 0 curator-stated, 33 derived-from-model
```

A paper that mixes the two says so in its `limits`, naming how many of each, because a selection
that spent one budget on two kinds of evidence under one name has not said what it did.

Measured on this corpus: **80 of 80** claims across the four dossiers carry a footprint derived
from the model, and none is curator-stated. What that number does not say is the reach — those
four are the only dossiers here, so the derivation covers 4 of the 31 seeded entries and none of
the other five classes.

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

## What a certificate produced under a budget says

A plan is only half of it. The other half is what the *certificate* has to admit when the plan was
followed — because a certification that attempts three of a paper's fourteen claims and passes all
three has demonstrated something much weaker than one that attempts all fourteen, and a reader who
cannot see the difference is being flattered. Attempting only the claims that pass is the cheapest
route to the word `reproduced`.

So a budgeted certificate carries the budget, the objective that spent it, and **every claim it did
not attempt, by id** — and the overall verdict is qualified for as long as one of them stands, the
same way a load-bearing assumption qualifies it.

The demonstration is the corpus's own clean pass. BIOMD0000001027 — metformin in mice, single oral
dose — is the only published certificate here reading an unqualified `reproduced`: fourteen claims,
all of them clean. Under a budget of three it stops being one:

```
OVERALL: partially-reproduced
  claims by verdict: reproduced=3, partial=0, failed=0, not-evaluable=0
  claims: 14 in the paper, 3 attempted, 11 left unattempted under a budget
...
NOT ATTEMPTED (chosen against by a budget, not judged)
  budget 3, objective: independent evidential value: set value less footprint overlap (exact)
  [Cmax-plasma] Plasma Cmax after a single 50 mg/kg oral dose in mice (source Table 1, ...)
  ... 10 more ...
  These claims were neither reproduced nor unreproduced — nothing was run for them.
```

Three things are load-bearing in that output and each is enforced rather than written:

- **The verdict counts sum to the attempt, so the paper's own total is printed beside them.**
  `reproduced=3` is a true sentence about a fourteen-claim paper and a misleading one on its own.
- **An unattempted claim never acquires a verdict.** It is not `not-evaluable` — that means
  Reprolith ran the claim and could establish nothing, which is a different statement about the
  paper — so it is a different shape entirely (`UnattemptedClaim`), invisible to every verdict
  counter, badge and gap report by construction.
- **The record cannot be edited into a better result.** A claim listed as both judged and
  unattempted is refused on the way in *and* on the way out, and the stored verdict is re-derived
  from the stored selection when a certificate is read back — so deleting the selection from a file
  to promote its own verdict makes the file unloadable rather than green.

A selection only ever runs in one direction: it can withhold a clean pass, never rescue a miss.

The join is `plan_under_budget`, which splits a paper's claims into the chosen set and the record
of the rest, and hands both to `certify_model`. Doing it in one place is what keeps a certificate's
"not attempted" list the exact complement of what it ran, and a selection made over some *other*
paper's claims is refused rather than quietly certifying whatever matched. The walk from dossier
footprints to certificate is `tests/test_budgeted_end_to_end.py`; on this paper the set-level
objective takes plasma, portal vein and adipose — score 2.592, witnessing 62 model elements —
where the ranking would have taken adipose, brain and heart (2.118, 23 elements).

## What it reaches today

Four papers — the metformin entries, which are the only ones in this repository with dossiers at
all. The other five model classes ship certificates and agreement reports but no dossiers, so
there is nothing for a selection to read there. That is a gap in what has been ingested, not in
this capability, and `select-claims` on an accession with no dossier says so rather than returning
an empty plan.

## Over MCP

The `select_claims` tool takes `accession` and `budget` and returns the same object the terminal
prints, `limits` included. See [mcp-server.md](mcp-server.md).
