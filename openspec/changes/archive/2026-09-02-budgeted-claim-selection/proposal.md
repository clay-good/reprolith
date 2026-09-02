## Why

The `claim-selection` capability can choose the best *set* of a paper's claims to reproduce within
a budget, and nothing in the repository can feed it. Two things are missing, and they are the whole
of this change:

1. **Nothing produces footprints.** Selection needs to know what each claim's verdict rests on, and
   that field is recorded by hand or not at all. Every dossier in the repository records none, so
   every selection the engine can make today reports that it optimized nothing — which is honest,
   and useless.
2. **Nothing consumes a selection.** A certificate says what was reproduced. It does not say what
   was *not attempted*, so a certificate covering three of a paper's eleven claims reads exactly
   like one covering a paper with three claims. That is the reading a budgeted attempt makes
   possible, and closing it is the reason to have budgets at all.

The first is not blocked on the manuscript extractor. A claim targets a quantity in a model, and
for an SBML-backed dossier the model itself says which parameters and species that quantity depends
on. A footprint derived from the *model's structure* is a measurement, not a guess — unlike one
matched out of the claim's free-text description, which this capability refuses on purpose. Where
the derivation cannot reach, the field stays empty and the report keeps saying so.

## What Changes

### 1. Footprints derived from model structure, with their provenance

Ingestion derives a claim's footprint from the reconstructed model: the parameters, species, and
compartments its target quantity's rate law transitively depends on, plus every gap reconstruction
must close to run it. The derivation is recorded as such — a footprint derived from structure is
distinguishable from one an extractor read from the paper, because the two carry different weight
and a reader must be able to tell them apart.

A claim whose target the model does not resolve gets no footprint. Partial derivation is the normal
case and the report already says what share of the pool it covered.

### 2. The claims dataset carries footprints

`datasets/pkpd_claims.json` and its siblings gain an optional per-claim footprint, so a
hand-contributed claim can state what it rests on without waiting for the derivation to reach its
class. This is where a curator's judgment enters, and it is the only place it enters.

### 3. A certificate records what was not attempted

When a reproduction runs under a budget, the certificate records the selection: which of the
paper's claims were attempted, which were not, the budget, and the objective. An unattempted claim
appears in the certificate as unattempted — never absent, and never as a verdict. The overall
verdict of a budgeted certificate is qualified by the selection, the way it is already qualified by
a load-bearing assumption: a paper is not "reproduced" on the strength of the third of its claims
somebody chose to run.

## Impact

- New: footprint derivation in ingestion; a selection record in the certificate; an optional
  footprint field in the claims datasets.
- Changed: a certificate produced under a budget carries a new field and a new qualification. A
  certificate produced without one is unchanged, byte for byte, so no published digest moves.
- Not in scope: extracting claims from a manuscript at all, which is the roadmap's own open item
  and which this change neither needs nor advances.
