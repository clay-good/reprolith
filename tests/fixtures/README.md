# Test fixtures

- `BIOMD0000000241.xml` — Shi1993 caffeine pressor-tolerance PK/PD model, retrieved from the
  BioModels repository (https://www.ebi.ac.uk/biomodels/BIOMD0000000241). BioModels
  manually-curated models are released under CC0 1.0 (public domain). Used to test SBML
  artifact-intake ingestion against a real model rather than a synthetic one.
- `BIOMD0000000948.xml` — Landberg2009 alkylresorcinol dose-response model
  (https://www.ebi.ac.uk/biomodels/BIOMD0000000948, CC0 1.0). Three of its species share the
  display name "AR" with distinct SBML ids; used to test that the engine resolves a species by
  its SBML id rather than the ambiguous column title.
