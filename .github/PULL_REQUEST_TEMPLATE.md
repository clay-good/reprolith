<!-- Thanks for contributing to Reprolith. Keep this short and concrete. -->

## What this changes

<!-- One or two sentences. What does this PR do? -->

## Type

- [ ] Verification decision (confirm / correct / reject a queued value)
- [ ] New candidate paper or ground-truth label
- [ ] Dossier / reconstruction correction
- [ ] Code or spec change
- [ ] Docs

## Related issue

<!-- The verification or candidate issue this resolves, e.g. "Resolves #123". -->

## Proof / rationale

<!-- For a corrected value: the right value and its source. For code: what you verified. -->

## Gates (must pass — CI enforces these)

- [ ] `openspec validate --strict` passes (specs stay consistent)
- [ ] `ruff check .` passes
- [ ] `mypy` passes
- [ ] `pytest -q` passes
- [ ] This change does **not** weaken any certificate's scope statement, assumption-qualification,
      or blind self-validation.
