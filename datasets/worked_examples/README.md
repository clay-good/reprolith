# Worked example — metformin PBPK reproduction

A real, end-to-end Reprolith certification of a published model, start to finish, on real data.
It is the first concrete instance of the bootstrap pipeline producing an honest, qualified
verdict — a walkable artifact a stranger can follow without Reprolith internals.

## The paper and the claim

- **Model:** Zake2021, PBPK model of metformin in humans, single oral dose
  ([BioModels BIOMD0000001028](https://www.ebi.ac.uk/biomodels/BIOMD0000001028), CC0).
- **Paper:** Zake et al., *PLOS ONE* 2021, [doi:10.1371/journal.pone.0249594](https://doi.org/10.1371/journal.pone.0249594) (open access).
- **Claim checked:** a single **1000 mg** oral dose gives a plasma **Cmax of 11.2 nmol/mL**
  (Chung dataset). The reference value comes from the manuscript, not from re-running the model,
  so the check is not circular.

## What Reprolith found

Run under the pinned COPASI engine, the model reproduces the reported Cmax to **0.4 %**
(simulated 11.25 vs reported 11.2 nmol/mL) — **but only after a load-bearing assumption**.

The model's dose input is metformin **free base**, while clinical doses are stated as the
**HCl salt**. Reprolith infers this from the model's own default (389.92 mg = 500 mg HCl
expressed as free base) and converts the stated 1000 mg HCl to 779.9 mg free base. Taken
naively — 1000 mg straight into a free-base input — the model overshoots by **26 %** and the
claim fails.

Because the reproduction rests entirely on that assumption, the certificate does not report a
clean `reproduced`: the claim is **reproduced (assumption-qualified)** and the overall verdict
is **partially-reproduced**. Reprolith never takes unqualified credit for its own guess.

This is the whole thesis in one case: the model *does* reproduce its paper, but reproduction
hinges on an under-specified detail (the salt-form dosing convention), and an honest system
surfaces that detail rather than hiding it.

## Files

- `Zake2021_metformin_human_single_PO.xml` — the CC0 model artifact.
- `metformin_reproduction_certificate.txt` — the rendered certificate.
- Reproduced by `tests/test_worked_example.py` (needs the `engine` extra).

## Scope and caveats

The certificate attests only to computational reproducibility, never biological or clinical
validity. The claim value (11.2 nmol/mL) was read from the paper text; a fuller ingestion would
cite the exact table/figure and check more than one claim. This is one worked example, not the
full blind test-set run.
