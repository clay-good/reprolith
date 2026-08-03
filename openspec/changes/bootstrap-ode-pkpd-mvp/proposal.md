## Why

Reprolith's thesis is only worth anything if a certificate it issues agrees with reality on
cases where reality is already known. So the first milestone is not "build the whole engine"
— it is **prove the loop closes on one model class, measured against ground truth**.

We choose ODE PK/PD compartmental models because:

- They are where our own sibling datasets already live, so we have the deepest domain footing.
- Their reproduction targets are crisp and standard (concentration/effect curves and derived
  metrics), which makes the oracle tractable and its tolerances defensible.
- A meaningful pool of PK/PD and kinetic models already carries **independent reproducibility
  labels** in public curation, giving us a blind test set that needs no wet lab and no
  permission from anyone.

The success of this milestone is a single, walkable artifact: **Reprolith reconstructs and
certifies a labelled set of PK/PD models, and its blind verdicts agree with the known
labels — with every disagreement explained.** That artifact is what we take to the
reproducible-modeling community to earn collaborators.

## What Changes

This change delivers a thin but complete vertical slice through the whole engine for the
`ode-pkpd` class only, plus the self-validation harness that judges it.

### 1. A minimal but real vertical slice

Deliver the smallest end-to-end path that still produces a genuine certificate:

- Catalog: create, tag as `ode-pkpd`, move an entry through the lifecycle, attach a
  ground-truth label, keep it blind from the verdict path.
- Ingestion: produce a PK/PD dossier — structure, parameters, dosing, claims — with
  provenance and explicit gaps, revisable by a reviewer.
- Reconstruction: emit a standard-format model + simulation recipe that a registered engine
  runs, with every gap-closure recorded as an attributed assumption.
- Oracle: per-claim `reproduced` / `partial` / `failed` / `not-evaluable` on curves and
  derived PK/PD metrics, with declared tolerance and root-caused failures.
- Certificate: a self-contained, scope-flagged, per-claim, qualification-preserving record.

### 2. MVP scope fences (explicit deferrals)

To keep the slice honest and shippable, this milestone **restricts** the class and **defers**
breadth. See the delta specs for the exact fences. In summary:

- In scope: single-subject, deterministic, simulation-level reproduction of **any** PK/PD
  model expressible as an ODE system that runs under the pinned engine — multi-compartment PK,
  nonlinear/saturable elimination, transit/lag absorption, effect-compartment and
  indirect-response PD, target-mediated disposition, and physiologically-based structures. The
  fence is the *method*, not the topology.
- Deferred (named, not forgotten): population / inter-individual variability, estimation
  reproduction from raw data, stochastic or spatial simulation, multi-engine corroboration,
  and non-PK/PD classes.

### 3. The self-validation harness and the discipline loop

- Assemble a blind test set of labelled PK/PD entries (target on the order of ~20 known
  reproducible + ~10 known-hard/irreproducible).
- Run the pathway blind, report per-entry and aggregate agreement with the labels, and treat
  every disagreement as a defect with a written note and a follow-up iteration.
- Nothing about this milestone is "done" until the agreement report exists and each
  disagreement is either fixed or explained.

### 4. The two surfaces, minimally

- The repository is the human/agent surface: entries, dossiers, bundles, and certificates
  live as reviewable files.
- A minimal MCP surface exposes read-only catalog/certificate queries and the inline
  deterministic linter check, so an agent can consume a verdict early — full lease-based work
  handoff over MCP is deferred.
