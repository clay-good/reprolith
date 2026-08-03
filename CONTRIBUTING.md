# Contributing to Reprolith

Reprolith reproduces published biomedical models and certifies whether they reproduce their own
results. It gets better in two ways, and **both need people who know the science**:

1. **Validate its judgment.** When Reprolith is not confident about a load-bearing value — a
   shaky extraction, an assumption it had to make, a verdict near its tolerance — it records its
   best estimate and opens a **verification issue**. Confirming, correcting, or rejecting these
   is the single most valuable thing an expert can do here.
2. **Grow and correct the catalog.** Propose a paper to reproduce, add a ground-truth
   reproducibility label, or fix a mis-extraction — as a pull request.

You do **not** need to understand Reprolith's internals to help. Every verification issue is
self-contained: the question, the source context, Reprolith's best guess and reasoning, and what
depends on it. If you know the modeling, you can decide.

## How the collaboration works

- **Verification issues** are Reprolith's questions to you. Answer in the issue: confirm,
  correct (with the right value and a source), or reject (with why). Your decision, your name,
  and your rationale become the record — and a correction triggers re-verification of everything
  that depended on it.
- **Pull requests** are how any change to the data or code lands. Reference the issue a PR
  resolves. The same automated gates run on every PR, whether it comes from a human or from
  Reprolith's own build loop — nobody gets a lower bar.
- **Certificates stay honest.** A result that only reproduced because of an assumption, or that
  rests on a value still awaiting your confirmation, is reported as *qualified* — never as a clean
  reproduction. Please help us keep it that way.

## The gates every change must pass

A change can only reach `main` if it passes, as required checks:

- `openspec validate --strict` — the specs stay consistent.
- `ruff check` — lint.
- `mypy` — types.
- `pytest` — tests, including the honesty invariants (determinism, inescapable scope,
  assumption-qualification).

Run them locally before opening a PR:

```bash
pip install -e ".[dev]"
ruff check .
mypy
pytest -q
```

(Spec validation uses the OpenSpec CLI: `npx @fission-ai/openspec validate --strict`.)

## The one rule we will not bend

**Reproducible is not correct, and neither is clinically valid.** Reprolith certifies only that a
model regenerates its own published results. No contribution may weaken a certificate's scope
statement, its assumption-qualification, or its blind self-validation. These are enforced in code
and in CI, and a change that erodes them fails the gates by design.

## Ways to start

- Answer an open **verification issue** labelled `pending-verification`.
- Open a **candidate paper** issue to nominate a model worth reproducing.
- Pick up a task from `openspec/changes/` or an item from
  `openspec/initiatives/catalog-backlog/roadmap.md`.

Thank you for helping make a literature that should be runnable, actually runnable.
