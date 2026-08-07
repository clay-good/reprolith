# Worked example — logical (Boolean-network) reproduction

A real, end-to-end Reprolith certification of a logical model, start to finish. It is the
logical-class counterpart of the [metformin PK/PD](../../worked_examples/README.md) and
[E. coli core FBA](../../constraint_based/worked_example/README.md) worked examples: the same
dossier-ingestion → oracle → certificate pipeline, driven by a third, distinct oracle —
discrete **attractor analysis**, not curve-matching or linear programming — producing an honest
verdict with an inescapable scope flag.

## The model and the claim

- **Model:** a **toggle switch** — two genes that mutually repress each other (`A = !B`,
  `B = !A`), the canonical bistable circuit — shipped as standard **SBML-qual** in
  [`model.xml`](model.xml) and ingested with `ingest_qual_sbml`.
- **Claims checked:** the two reported steady states the circuit is famous for — *A-ON*
  (`A=1, B=0`) and *A-OFF* (`A=0, B=1`). Each is checked for membership in the network's
  computed fixed points, so the reference is the discrete state itself, not a re-run number.

The result is [`certificate.txt`](certificate.txt): both steady states reproduce, so the overall
verdict is a clean **reproduced** — carrying the same scope flag as every other class.

## Why the update scheme is the teaching point

Under **synchronous** updating the toggle has three attractors: the two fixed points *and* a
2-cycle between `(0,0)` and `(1,1)`. Under **asynchronous** updating that 2-cycle vanishes — its
states become transient — and only the two fixed points remain. The fixed points are the same
either way, which is exactly why:

- a **steady-state** claim (like the two here) is robust to an unstated update scheme, but
- an **attractor-set** claim that includes the cycle is *scheme-sensitive*: reporting only the two
  fixed points reproduces under `UpdateScheme.ASYNCHRONOUS` but fails under
  `UpdateScheme.SYNCHRONOUS` (the extra 2-cycle is surfaced, not hidden).

That is why an unstated update scheme is a first-class gap for this class, and why
`judge_attractor_set` takes the scheme it should judge under. See
[docs/logical-class.md](../../../docs/logical-class.md) for the full oracle.

## Regenerate it

[`tests/test_logical_worked_example.py`](../../../tests/test_logical_worked_example.py) ingests
`model.xml`, re-certifies the two claims, and asserts the rendered certificate matches
`certificate.txt` byte for byte — so this artifact is regenerable from the repository alone.
