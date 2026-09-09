# Spatial (reaction-diffusion) milestone — blind agreement against closed-form ground truth

The walkable result of `scripts/run_spatial_milestone.py`: three 1-D diffusion systems whose profile
is known in closed form, flowed through the same catalog lifecycle, certificate format, agreement
report, and scope flag as every other class. It is the sixth class demonstrating the shared
contracts generalize — this time with a *spatial PDE* solver whose reproducible result is a
concentration profile over space, judged by the shared curve oracle.

## What is here

- [`catalog.json`](catalog.json) — five entries, tagged `spatial`, each with a ground-truth label
  withheld from the verdict path, advanced to `certified`: three diffusion profiles, a morphogen
  gradient's decay length, and an invasion front's speed.
- [`certificates/`](certificates/) — one certificate per entry, each certifying that the
  finite-difference result reproduces its closed form.
- [`agreement_report.json`](agreement_report.json) — **5/5** agreement.

## Non-circular and honest

The ground truth is closed-form mathematics: the diffusion of a Gaussian is exactly a Gaussian whose
variance grows by `2·D·t`. Each certificate is produced from only the initial profile and the pinned
discretization (spatial step, time step, diffusivity), never the label, and the pinned discretization
makes it byte-reproducible. A result resting on a choice Reprolith made is never published as a
clean pass, and for a month every profile here read **partially-reproduced** on exactly that
ground: the solver imposed a zero-flux (Neumann) wall the source had not stated.

They read `reproduced` now, and the change is a measurement rather than a relaxation. The
reference is the free-space Gaussian — the domain a closed form is derived in has no walls — so
each claim states `boundary="unbounded"`, which this solver cannot run and therefore has to
*check*: two of its edge rules bracket free space (one reflects what reaches it, the other absorbs
it), so the distance between those two runs bounds what the finite grid costs. Here that bound is
2e-07 to 3e-05 against a budget of 1e-02 — a tenth of the pass tolerance, and it must also come
in under a tenth of the distance each claim's own answer sits from its nearest verdict line, so a
claim landing a hair from its threshold cannot be decided by the substitution either. A wall
measured not to reach the profile is not an assumption about it, so nothing is qualified. Judged blind like
everything else: a run that could no longer show this would disagree with its label rather than
quietly publish a clean pass. A domain narrow enough for the walls to matter abstains instead, with
the number that made it abstain (`tests/test_spatial_unbounded_claim.py`).

One honest limit on how independent these three systems are: each picks its time step as a fixed
fraction of the stability limit (`dt = 0.2·dx²/D`), so the reference variance `2·D·steps·dt` works
out to `0.4·dx²·steps` — the diffusivity cancels. The three entries differ in mass, initial
variance, and step count, but they do not independently exercise three diffusivities. They are a
real test of the solver against closed-form mathematics; they are not three independent draws.

Regenerate with `python scripts/run_spatial_milestone.py` (no extras, no network).
