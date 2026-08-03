# Catalog Backlog

Status: active planning artifact.

This initiative is Reprolith's prioritized build-and-seed queue — the ordered set of model
classes, source integrations, and enabling capabilities that turn the ODE PK/PD MVP into a
powerful, general, self-refilling engine. It is intent and ordering, not a behavioral
contract; each item graduates into a spec and a change when it is picked up.

## How to read this

- The ranked items live in [`roadmap.md`](roadmap.md).
- Each item is written as a structured stub: what it is, why it ranks where it does, its oracle
  or approach, its seed source, difficulty, dependencies, and a concrete done-when.
- An item is not "started" until it has its own spec delta and a change under
  `openspec/changes/`. This file never replaces those.

## Prioritization rubric

Items are ranked by a simple, stated formula so the order is explainable, not a matter of taste:

**priority ≈ (value × readiness) ÷ cost**, with two hard rules on top:

1. **Ground-truth-first.** Anything that keeps blind self-validation possible outranks pure
   breadth. A class or source with independent reproducibility labels beats one without.
2. **Momentum matters.** Early items should produce walkable certificates and grow the catalog
   fast, because the first outside collaborators are won with artifacts, not promises.

Where:

- **value** — how much the item advances the mission (reproductions produced, "what was
  missing" reports generated, credibility with the reproducible-modeling community).
- **readiness** — how much of the input already exists in a standard, runnable form.
- **cost** — engineering effort and new oracle machinery required.

## The through-line

Two things must stay true as the backlog is worked:

- **The engine generalizes.** Each new model class must reuse the shared contracts (catalog,
  dossier, assumptions, certificate, scope flag) and specialize only its structure, targets,
  tolerances, and failure modes. A class that cannot fit becomes a change to the shared spec,
  never a private fork.
- **The backlog never drains.** Seeding runs continuously and ground-truth-first, so there is
  always well-scoped, prioritized, self-validatable work to claim.
