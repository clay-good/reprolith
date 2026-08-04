# Outreach shortlist — reproducible-modeling community

Bootstrap milestone task 8.3. Who to approach first, why they fit, and how to engage. The
list is deliberately organization- and venue-level: Reprolith's value proposition is a
verdict-and-certificate on the reproducibility of published models, so the first audiences are
the groups that already curate, standardize, or study that reproducibility.

## Tier 1 — reproducibility infrastructure (most aligned)

| Target | Why it fits | How to engage |
|---|---|---|
| **BioModels team, EMBL-EBI** | Curates the models Reprolith's test set is drawn from; their manual-curation status is the ground-truth signal Reprolith validates against; they run active model-verification work (e.g. the 2025 repository-verification effort). | Share the blind agreement report on the seeded PK/PD set; offer the certificate as a curation aid; propose a pilot on their non-curated backlog. |
| **Center for Reproducible Biomedical Modeling (reproduciblebiomodels.org)** | NIH-funded center whose mission is exactly Reprolith's; produces BioSimulators / runBioSimulations (the containerized engine registry Reprolith pins) and FROG analysis for constraint-based models. | Position Reprolith as a certificate layer on top of BioSimulators; align on engine pinning and the "what was missing" report. |
| **BioSimulators / runBioSimulations** | The registered-engine ecosystem Reprolith targets for portable, re-runnable bundles. | Contribute the COPASI-pinned bundles and confirm cross-engine parity as a future step. |

## Tier 2 — standards community

| Target | Why it fits | How to engage |
|---|---|---|
| **COMBINE (co.mbine.org)** | Coordinates SBML, SED-ML, and the OMEX/COMBINE archive — the exact standards Reprolith's bundles target. | Present at the annual COMBINE forum / HARMONY hackathon; propose the certificate as a standard artifact alongside SED-ML. |
| **SED-ML and OMEX maintainers** | Reprolith's simulation recipes and bundles are only as portable as these standards; BioModels' own SED-ML coverage is known to be partial and error-prone, which is precisely the gap Reprolith's determinism harness surfaces. | Feed back concrete recipe/archive validation failures found during reconstruction. |

## Tier 3 — pharmacometrics / PK-PD (the MVP's domain)

| Target | Why it fits | How to engage |
|---|---|---|
| **International Society of Pharmacometrics (ISoP)** | The professional home of the PK/PD modelers whose papers are the MVP's scope. | A reproducibility-focused talk or workshop; recruit reviewers for dossier corrections. |
| **DDMoRe / open pharmacometrics tooling communities** | Model-encoding and exchange standards for pharmacometrics, adjacent to the SBML path. | Explore a PK/PD-native encoding path beyond SBML. |

## Tier 4 — publication venues

| Target | Why it fits | How to engage |
|---|---|---|
| **Molecular Systems Biology** | Published Tiwari et al. 2021 (doi:10.15252/msb.20209982), the reproducibility study Reprolith's labels rest on. | A follow-up piece: automated certification on the un-curated tail. |
| **CPT: Pharmacometrics & Systems Pharmacology** | The PK/PD-systems-pharmacology venue closest to the MVP class. | A methods/tools paper once the milestone artifact exists. |
| **PLOS Computational Biology** | Broad, reproducibility-friendly venue for a tools contribution. | Software/methods submission. |

## Notes

- Organizations and public projects only; no individuals are listed. Roles and affiliations
  evolve, so confirm current contacts before reaching out.
- Sequence: Tier 1 first (they own the ground truth and the engine registry, so a pilot there
  is the highest-credibility entry point), then standards, then domain societies, then
  publication once the milestone artifact and findings note exist.
