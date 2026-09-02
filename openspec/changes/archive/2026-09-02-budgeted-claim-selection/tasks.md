# Tasks — budgeted-claim-selection

Each task names how it is verified. Do not mark one done until its verification holds.

## 1. Footprints from model structure

- [x] 1.1 Resolve a claim's target quantity to a model element, and collect the parameters, species, and compartments its rate law transitively depends on → verify: on the metformin model, a claim on a plasma species yields the parameters its rate law names and nothing else, checked against the SBML by hand
- [x] 1.2 Include in the footprint every gap reconstruction must close to run the claim → verify: a dossier with a load-bearing dosing gap puts that gap in the footprint of every claim whose scenario doses — **measured and rejected, not built** (`tests/test_footprint_gaps.py`): every load-bearing gap in this corpus is a property of the *model*, not of a claim's run, so the rule adds the same five elements to all 33 footprints. Mean pairwise overlap 0.251 -> 0.380 and the spread that discriminates 0.955 -> 0.864, and the selector then returns a smaller set than the budget allows (3 claims at a budget of 4, and 3 at a budget of 5). Reopens by itself if a dossier ever records a gap only some claims need
- [x] 1.3 Record the derivation's provenance, so a derived footprint is distinguishable from an extracted one → verify: the selection report names how each footprint was arrived at, and a mixed dossier shows both — `FootprintOrigin`, refused when a footprint states none on both the build and load paths
- [x] 1.4 Leave the footprint empty where the target does not resolve → verify: a claim naming a quantity absent from the model selects with no footprint and the report counts it as uncharacterized

## 2. Curator-supplied footprints

- [x] 2.1 Accept an optional footprint per claim in the claims datasets → verify: a dataset without the field loads byte-identically to today, and one with it reaches the selector
- [x] 2.2 Refuse a footprint element that is neither derivable nor anchored in the dossier *silently* — report it → verify: an unanchored element appears in the report, and the load does not fail

## 3. A certificate that says what it did not attempt

- [x] 3.1 Record the selection in a certificate produced under a budget: attempted claims, unattempted claims, the budget, and the objective → verify: a budgeted run over a five-claim paper with a budget of three lists two unattempted claims by id — done on a real one instead: `tests/test_budgeted_end_to_end.py` runs BIOMD0000001027 at a budget of three and names the eleven, and `tests/test_budgeted_certificate.py` holds the five-claim case
- [x] 3.2 An unattempted claim appears as unattempted, never as a verdict and never absent → verify: no verdict counter includes it, and the claim count in the render matches the paper's, not the attempt's
- [x] 3.3 Qualify the overall verdict of a budgeted certificate by its selection → verify: a paper whose attempted claims all reproduce does not report an unqualified `reproduced` while claims were left unattempted — the corpus's one clean pass, budgeted to three of fourteen, comes back `partially-reproduced`
- [x] 3.4 A certificate produced without a budget is unchanged → verify: every published digest in `datasets/` regenerates identically — every committed certificate is reloaded and re-serialized through the new load path and compared to its stored bytes

## 4. Surfaces and record

- [x] 4.1 Extend the CLI and MCP selection surfaces with the derivation's provenance → verify: parity test passes and both surfaces show the same footprint origins
- [x] 4.2 Write the finding up in `docs/findings-note.md` with measured numbers from the corpus → verify: the note states what share of the corpus the derivation reached — 80 of 80 claims derived, across the 4 dossiers that exist of 31 seeded entries; held by `tests/test_footprints.py`
