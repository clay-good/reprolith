# Reading a figure's values in

Seven of the ten open-access papers in this repository's PK/PD test set state their results in
**figures** and nowhere else. Reading a paper's tables closes the rest, and reading its prose was
built and measured to close nothing further ([`findings-note.md`](findings-note.md)). Figures are
the whole of the remaining reach, and until now a claim whose values live in one abstained: the
oracle had the wider tolerance a figure deserves, ingestion had the claims — a shipped SED-ML
document says exactly which curves a paper shows — and nothing could supply a value.

This page is the intake half of that. **Reprolith does not digitize anything.** No pixels are read
here. A curator reads the curve off the picture with a plot digitizer, and what this handles is the
part the digitizer cannot: saying whether the reading is usable as a reference, and putting it on
the grid the run is sampled at.

## The file

One file is one figure panel: the axes are stated once, and every series in it was read off them.

```json
{
  "figure": "Figure 3A",
  "digitizer": "WebPlotDigitizer 4.7",
  "x_axis": {"minimum": 0, "maximum": 24, "unit": "h"},
  "y_axis": {"minimum": 0.01, "maximum": 10, "unit": "nmol/mL", "scale": "log10"},
  "series": [
    {"claim": "fig3a-plasma", "curve": "plasma", "points": [[0.5, 0.2], [2, 4.0], [24, 0.05]]}
  ]
}
```

Start from a template rather than a blank file, because the one mechanical part of this is also
the one nobody can guess — a claim id read off a SED-ML document is
`plot_0__plot_0_0_0__plot_0_0_1`, it has to match exactly, and a digitization paired with an id the
dossier does not carry is refused:

```bash
reprolith figure-template --sedml experiment.sedml --out figure3a.json
reprolith figure-template model.omex --out figure3a.json      # or straight from the archive
```

It writes the ids and the curve each one plots, and leaves blank everything that is a *reading*:
the figure, the tool, both axis ranges, and every point. None of those can be derived from a
document, and a template that filled in an axis range would be stating what a picture shows.
Handed straight back, `figure-check` names every blank still left rather than refusing on whichever
one it reaches first.

`claim` is the dossier claim these values are the reference for. That pairing is the curator's:
no rule here decides that the upper curve of Figure 3A is the plasma claim rather than the liver
one, exactly as no rule decides which table cell a reported Cmax came from.

```bash
reprolith figure-check --series figure3a.json                          # the reading, on its own
reprolith figure-check --series figure3a.json --sedml experiment.sedml # ...and its pairing
reprolith figure-check --series figure3a.json model.omex               # or straight from the archive
```

It reads the file, says what each series carries, and exits non-zero when it cannot trust one. It
runs no model and judges no claim, and it says so.

Handed the document as well, it checks the pairing itself against the curves that document plots.
That matters because the pairing is the half of the file a curator did not write freehand and
cannot verify by looking at it: the ids came out of a template, and a typo, a renamed model output,
or a digitization filled in against an older document produces a file that is internally perfect
and paired with nothing. The three refusals below that are *about the pairing* — an unknown claim,
a claim that already has values, a claim that is not a target — were reachable only from
`attach_digitized_values`, which is to say only from Python, and only once somebody else ran the
join. `figure-check` and the join now ask the same function, so the way in and the way out cannot
disagree about what a bad pairing is, and every fault is named at once rather than the first one
reached.

Two things it reports rather than refuses. The curves the document plots that this file does not
read: a curator reads one panel at a time, and a partial digitization is the ordinary case — but a
report that said "clean" over one of four curves would read as four. And, when no document is
given, that the ids were **not checked** — a clean report standing in for a check nobody made is
the shape this repository has been caught by before.

## What it refuses, and why each one earns its place

| Refused | Why |
| --- | --- |
| A series naming no figure or no digitizer | A digitized point is a *measurement of a picture*. A reference value with no statement of where it came from is the defect this repository was already caught by once, in the other direction: a claim's Cmax recorded as a number its paper does not print. |
| A point outside the axes the curator states | Every digitizer works by calibrating two axis points and mapping pixels through them. Get that wrong and the values come out ordered, smooth, plausible and wrong by a constant factor — the most confident wrong answer available, and invisible to every check downstream. A reading off the top of its own axis is the cheapest evidence it happened. |
| Two readings at one x, or a single point | Two values for one place is not a curve, and one point is not one either. |
| Two curves paired with one claim | Which curve a claim reads is the curator's statement, and two of them is not one. |
| Resampling outside the digitized span | Past the last point that was read there is no reference. Returning the last read value there compares the model against the edge of a picture. |
| Giving values to a claim that has them | A curve plotted from a data file the archive ships carries the paper's own recorded series. Replacing that with a reading off a picture of it is a downgrade performed silently. |
| Giving values to a non-targetable claim | A `report`'s data set is retained non-targetable on purpose; handing it values promotes it into a result the paper never staked. That is a [tracked revision](../openspec/specs/paper-ingestion/spec.md), not a side effect of attaching a figure. |

## Onto the run's grid

A curve claim is judged point against point, so the reference has to sit on the run's own
`steps + 1` uniform samples over `[0, duration]`.

```python
from reprolith import read_digitized_figure, attach_digitized_values, curve_reference

series = read_digitized_figure(Path("figure3a.json").read_text())
claims = attach_digitized_values(dossier.claims, series, times=[24.0 * i / 100 for i in range(101)])
```

Between two read points the reference is a straight line **in the axis's own scale**. That matters
and is not cosmetic: an exponential decay is a straight line on a log axis and is recovered
exactly, while reading the same two points linearly puts the midpoint of a decade-wide gap 81%
high — and half of pharmacokinetic figures are drawn on log axes.

What is left uncovered is stated rather than fixed. A claim judged on a grid far finer than the
reading is being judged partly against the curator's interpolation, and the digitized-figure
tolerance — 0.20 pass against a printed number's 0.10 — is what covers it. So `figure-check`
reports the widest gap between readings as a fraction of the span, and does not judge it: how much
of a comparison rests on a straight line is the curator's to weigh, not a threshold this command
invented.

The reference kind is always `digitized-figure`. A value read off a picture cannot be recorded as a
printed number, so the wider band it must be judged in is not escapable by attaching it.

## What the certificate then says

The join runs end to end: a SED-ML document says which curve the paper plots, the curator's file
says what that curve read, and the certificate carries a verdict where it used to carry an
abstention. The claim line names both halves and marks itself, so a reader can see the number was
read off a picture rather than printed:

```
  [c0] A: reproduced [figure-reading] (source SED-ML plot2D 'plot_0' (Figure 1), curve 'c0';
      values from Figure 1, A (digitized from the figure with WebPlotDigitizer 4.7)
      via curve-normalized-distance, tol=reproduced<=0.2, partial<=0.4 (class-default))
```

The marker earns its place because the widened band was previously invisible as a *reason*: the
human form printed `<=0.2` and nothing said it is `<=0.2` because the reference is a measurement of
a picture. Only figure-read claims carry it, so no certificate already published renders
differently.

`tests/test_digitized_figure_end_to_end.py` walks that path with nothing hand-written between the
document and the certificate — and shows the other side of it, which is worth stating plainly: the
figure band is **wide**. A model decaying half as fast as the curve it is judged against still
passes it (normalized distance 0.18 against a 0.20 budget), because the distance is measured
against the reference's own range and a decay's disagreement lives in a tail that range dwarfs. The
[loop record](discipline-loop.md) already calls that tolerance declared rather than measured. This
is the first thing to exercise it, and it is a test rather than a certificate.

## The other side of it, told to the author

The same fact is worth saying before a paper is published rather than after. `archive-check` lists
every curve a document plots with no values behind it, says what that costs a reproducer, and names
the cheap way out — ship the series as a data file the document points at. It is reported and never
gated on: a document that plots its curves is doing what SED-ML is for, and an archive marked "not
ready" for it would tell almost every honest author their work is broken. See
[`author-check.md`](author-check.md).

## The limit that remains

**No published figure is in this corpus.** This reader is validated against series generated from
functions whose value at every point is known — the same fence the population simulator and the
re-fitting engine carry: mathematics, not a paper's picture. What it needs next is a curator's
digitization of a real figure from a paper this repository already carries, and the digitization
itself is a human act this repository does not perform.
