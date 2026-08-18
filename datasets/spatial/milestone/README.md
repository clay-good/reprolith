# Spatial (reaction-diffusion) milestone — blind agreement against closed-form ground truth

The walkable result of `scripts/run_spatial_milestone.py`: three 1-D diffusion systems whose profile
is known in closed form, flowed through the same catalog lifecycle, certificate format, agreement
report, and scope flag as every other class. It is the sixth class demonstrating the shared
contracts generalize — this time with a *spatial PDE* solver whose reproducible result is a
concentration profile over space, judged by the shared curve oracle.

## What is here

- [`catalog.json`](catalog.json) — three entries, tagged `spatial`, each with a ground-truth label
  withheld from the verdict path, advanced to `certified`.
- [`certificates/`](certificates/) — one certificate per system, each certifying that the
  finite-difference profile reproduces the analytical Gaussian.
- [`agreement_report.json`](agreement_report.json) — **3/3** agreement.

## Non-circular and honest

The ground truth is closed-form mathematics: the diffusion of a Gaussian is exactly a Gaussian whose
variance grows by `2·D·t`. Each certificate is produced from only the initial profile and the pinned
discretization (spatial step, time step, diffusivity), never the label, and the pinned discretization
makes it byte-reproducible. The verdicts are clean **reproduced** — a spatial reproduction is
deterministic, so unlike the stochastic class it carries no sampling qualification.

One honest limit on how independent these three systems are: each picks its time step as a fixed
fraction of the stability limit (`dt = 0.2·dx²/D`), so the reference variance `2·D·steps·dt` works
out to `0.4·dx²·steps` — the diffusivity cancels. The three entries differ in mass, initial
variance, and step count, but they do not independently exercise three diffusivities. They are a
real test of the solver against closed-form mathematics; they are not three independent draws.

Regenerate with `python scripts/run_spatial_milestone.py` (no extras, no network).
