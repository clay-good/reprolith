# Tasks — bootstrap-ode-pkpd-mvp

Work top to bottom. Each phase ends with a written note in the entry/loop record. Do not mark
a phase done until its verification holds.

## 0. Foundations

- [ ] 0.1 Confirm the open-standard targets and one pinned registered engine the MVP will use → verify: a trivial hand-built model runs under the pin and returns a known output
- [ ] 0.2 Define the on-disk shapes for entry, dossier, reconstruction bundle, and certificate → verify: an empty example of each validates against its shape
- [ ] 0.3 Establish the determinism harness (same inputs + pin ⇒ same certificate) → verify: two runs of the trivial model produce byte-identical certificates modulo run metadata

## 1. Catalog (MVP slice)

- [x] 1.1 Implement entry creation, `ode-pkpd` tagging, and the lifecycle state machine → verify: an entry can traverse every state with recorded transitions
- [x] 1.2 Implement the ground-truth label field with blind withholding from the verdict path → verify: the verdict path provably cannot read the label
- [x] 1.3 Implement de-duplication across identifiers → verify: the same paper under two IDs resolves to one entry
- [ ] 1.4 Seed the blind test set: ~20 known-reproducible + ~10 known-hard PK/PD entries → verify: each carries a label, source, and expected verdict

## 2. Ingestion (PK/PD dossier)

- [ ] 2.1 Produce a PK/PD dossier: compartment structure, rate expressions, PD link, parameters+units, initial conditions, dosing → verify: on a hand-checked paper, every element cites a source location
- [ ] 2.2 Enumerate targetable claims (curves and reported metrics) with reference data or figure-reference marking → verify: claim count and types match a manual read
- [ ] 2.3 Record gaps and extraction-confidence; never fill gaps at this stage → verify: a paper with a missing parameter yields a gap, not a value
- [ ] 2.4 Support reviewer correction as a tracked revision → verify: a correction is applied and the original remains retrievable

## 3. Reconstruction (PK/PD)

- [ ] 3.1 Build a standard-format model + simulation recipe from a dossier for the in-scope PK/PD structures → verify: the bundle validates and runs under the pin
- [ ] 3.2 Record every gap-closure as an attributed assumption with alternatives and basis → verify: each assumption is present and attributed to Reprolith, not the paper
- [ ] 3.3 Flag load-bearing assumptions → verify: an assumption that changes a claim's outcome is flagged
- [ ] 3.4 Adopt-and-verify a shipped model when present; surface mismatches with the dossier → verify: an author-supplied model is labelled as such; an injected mismatch is reported

## 4. Oracle (PK/PD)

- [ ] 4.1 Implement curve comparison and derived-metric comparison with declared tolerances → verify: a known-good reconstruction reproduces; a perturbed one fails
- [ ] 4.2 Implement class-default tolerances and principled overrides → verify: default is recorded when unset; override without rationale is rejected
- [ ] 4.3 Implement `not-evaluable` abstention → verify: a figure-only claim with no digitizable data abstains rather than guesses
- [ ] 4.4 Implement root-cause attribution from the PK/PD failure-mode set, with paper-vs-reconstruction hypothesis → verify: each non-pass carries a category and an implicated element
- [ ] 4.5 Guarantee determinism of the verdict and discrepancy → verify: repeated evaluation is identical

## 5. Certificate

- [x] 5.1 Emit a self-contained machine- and human-readable certificate from one data source → verify: both renderings agree
- [x] 5.2 Derive the overall verdict by the stated rule; show per-verdict claim counts → verify: a mixed result reports `partially-reproduced`, never `reproduced`
- [x] 5.3 Enforce assumption-qualification and the inescapable scope flag → verify: an assumption-qualified pass cannot render as unqualified `reproduced`; the scope flag cannot be emptied
- [x] 5.4 Emit the structured "what was missing" gap report for anything short of full reproduction → verify: a blocked entry lists precise missing inputs tied to claims
- [x] 5.5 Implement supersession/versioning → verify: re-certifying under a new pin links and preserves the prior certificate

## 6. MCP surface (minimal)

- [x] 6.1 Expose read-only catalog/status/certificate/gap queries → verify: queries change no state and return the certificate's full qualifications
- [ ] 6.2 Expose the inline deterministic linter check (model + claim ⇒ verdict) → verify: same submission yields same verdict
- [x] 6.3 Guarantee the scope flag travels with every returned verdict → verify: no code path returns a bare boolean
- [x] 6.4 Confirm surface parity with the repository → verify: same entry reports the same verdict through both

## 7. Self-validation and the discipline loop

- [ ] 7.1 Run the full pathway blind over the test set → verify: every entry yields a certificate
- [ ] 7.2 Produce the agreement report (per-entry and aggregate) vs. ground-truth labels → verify: the report exists and is reproducible
- [ ] 7.3 For every disagreement, write a defect note, fix the responsible stage, and re-run → verify: no unresolved disagreement remains without a written explanation
- [ ] 7.4 Freeze the evidence-driven PK/PD failure-mode catalogue and tolerance defaults from what the loop taught us → verify: each default and category traces to a loop note

## 8. Milestone artifact

- [ ] 8.1 Assemble the walkable result: the labelled set, the certificates, and the agreement report → verify: a stranger can follow it end to end without Reprolith internals
- [ ] 8.2 Write the short findings note (what reproduced, what didn't, what the field under-specifies most) → verify: claims in the note trace to certificates
- [ ] 8.3 Identify the first outreach targets in the reproducible-modeling community → verify: a concrete, named shortlist exists
