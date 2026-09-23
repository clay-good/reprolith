# Reprolith

**Point it at a modeling paper. Get back proof of whether the model reproduces its own results.**

About half of published biomedical models can't be reproduced from their own paper. Reprolith
rebuilds the model, re-runs it, and checks every result against the paper's own figures and
tables. You get a **certificate**: for each result, reproduced, partially reproduced, or not, and
why.

## Why it works

Checking a biology claim usually takes a lab. Checking a paper's *figure* doesn't: it's a
computational result, and re-running the model either produces it or it doesn't. That test is
free, repeatable, and exact to a stated tolerance, and Reprolith does nothing else.

## What you get

- **A verdict per result, not per paper.** A curve has to match on average *and* at its worst
  point, so a doubled peak can't average its way into a pass.
- **Honesty built in.** If a result only reproduced because Reprolith had to assume a missing
  value, the certificate says so. It never takes credit for its own guesses.
- **A list of what was missing.** When a paper falls short, you get the exact parameter, unit, or
  condition it left out, which is the thing an author can actually fix.
- **The same answer every time.** Pinned engines, deterministic runs, and a certificate anyone can
  regenerate.

A certificate says one thing only: the model regenerates its own published results. That is not
the same as biologically correct, and it is not clinical advice. Every certificate says so.

## Try it

Work from a clone; the published certificates are repository data.

```bash
pip install -e ".[dev]"              # add ,engine to run models (COPASI + libSBML)
reprolith catalog                    # the papers in the catalog
reprolith self-validation            # how often Reprolith's verdicts match known answers
reprolith certificate <digest>       # one certificate, human-readable
reprolith gaps <digest>              # what the paper left out
reprolith archive-check <file.omex>  # for authors: what a reproducer will find in your archive
```

`reprolith --help` lists every command. AI agents get the same answers over MCP: run
`reprolith-mcp` and see [docs/mcp-server.md](docs/mcp-server.md).

## Where it stands

Pre-alpha, and honest about it. Six model classes are built and self-validated in the open:
pharmacokinetic/pharmacodynamic, constraint-based, kinetic, logical, stochastic, and spatial.
Every certificate, blind track record, and known limit is published in this repository.

For the full account, including every number, every command, and what isn't built yet, read
[docs/in-depth.md](docs/in-depth.md). The spec is in [openspec/](openspec/), and
[CONTRIBUTING.md](CONTRIBUTING.md) covers building and testing.

## License

Code: MIT ([LICENSE](LICENSE)). The data Reprolith produces (certificates, catalog, reports) is
CC BY 4.0 ([LICENSE-DATASET](LICENSE-DATASET)). Third-party model files under `datasets/` keep
their own licenses, and some are non-commercial: see
[datasets/THIRD-PARTY-NOTICES.md](datasets/THIRD-PARTY-NOTICES.md).
