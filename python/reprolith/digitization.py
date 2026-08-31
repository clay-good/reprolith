"""Reading a figure's values in, when somebody has already read them off the picture.

Every published claim in this repository whose values live in a **figure** abstains. The
tolerance for such a claim exists (``ReferenceKind.DIGITIZED_FIGURE``, and a band three to five
times wider than a printed number's), the claims themselves are enumerated — a shipped SED-ML
document says exactly which curves a paper shows — and there has never been a way to give one a
value. So `certify_curves` runs the model and then throws the run away: ``not-evaluable``, with
the reason on the claim line. Measured on the seeded set, seven of the ten open-access papers put
their results in figures and nowhere else, which is the whole of the remaining reach.

This closes the intake half of that. It does **not** digitize anything: no pixels are read here,
and reading them is a curator's job with a plot digitizer. What arrives is that tool's output —
points in the figure's own units — and what this module does is the part a digitizer cannot do:
say whether the series is usable as a reference, and put it on the grid the run is sampled at.

Four refusals earn their place, and each one is a way a digitization is wrong rather than
imprecise.

``a series with no provenance is not read``
    The figure, the curve within it, and the tool that read it are required. A reference value
    with no statement of where it came from is the defect this repository was already caught by
    once, in the other direction: a claim's reported Cmax recorded as a number its paper does not
    print. A digitized point is a *measurement of a picture*, and it travels as one.

``a point outside its own axes is a calibration error, not a reading``
    Every digitizer works by calibrating two axis points and mapping pixels through them. Get the
    calibration wrong and the points come out plausible, ordered, smooth, and wrong. A series
    whose points fall outside the axis range the curator states is refused by name — the cheapest
    check that catches the failure that produces the most confident wrong answer available.

``nothing is extrapolated``
    A run sampled past the last point the curator read is not compared against a guess. Resampling
    outside the digitized span raises, naming the time and the span, so a claim is judged over the
    window the figure actually shows or not at all.

``a value is never given to a claim that has one, or to one that is not a target``
    Overwriting reference data would replace a number the archive shipped — the paper's own
    recorded series — with one read off a picture of it. And a `report`'s data set is retained
    non-targetable on purpose; handing it values would promote it into a result the paper never
    staked. Both are the curator's call through a tracked revision, not this function's.

What remains uncovered, and is stated rather than fixed: between two read points the reference is
a straight line, in the axis's own scale, and a claim judged on a grid far finer than the reading
is being judged partly against that interpolation. The digitized-figure tolerance is what covers
it, and :func:`series_resolution` reports the largest gap so the curator can see how much work it
is doing. No published figure is in this corpus, so this reader is validated against series
generated from known functions — mathematics, not a paper's picture.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .dossier import DossierClaim
from .oracle import ReferenceKind

#: Slack on the axis-range check, as a fraction of the axis span in its own scale. A digitizer
#: writes a point that sits on the frame as the frame value plus float noise; this absorbs that
#: and nothing else. A mis-calibration is off by percents, not by parts in a billion.
_FRAME_SLACK = 1e-9


class AxisScale(str, Enum):
    """How the figure's axis is drawn — which is how a reading between two points is joined."""

    LINEAR = "linear"
    LOG10 = "log10"


@dataclass(frozen=True)
class Axis:
    """One axis of the panel a series was read off: its range, its unit, and its scale."""

    minimum: float
    maximum: float
    unit: str
    scale: AxisScale = AxisScale.LINEAR

    def __post_init__(self) -> None:
        if not self.unit.strip():
            raise ValueError("every axis must state its unit; an unstated unit is not a reading")
        for bound in (self.minimum, self.maximum):
            if not math.isfinite(bound):
                raise ValueError(f"axis bounds must be finite, not {bound}")
        if self.minimum >= self.maximum:
            raise ValueError(
                f"axis minimum {self.minimum} is not below its maximum {self.maximum}"
            )
        if self.scale is AxisScale.LOG10 and self.minimum <= 0.0:
            raise ValueError(
                f"a log10 axis cannot reach {self.minimum}; its minimum must be above zero"
            )

    def transform(self, value: float) -> float:
        """The value in the scale the axis is drawn in, which is where interpolation is linear."""
        return math.log10(value) if self.scale is AxisScale.LOG10 else value

    def untransform(self, value: float) -> float:
        return 10.0**value if self.scale is AxisScale.LOG10 else value

    def contains(self, value: float) -> bool:
        """Whether a read point falls inside the axes the curator says it was read off."""
        if not math.isfinite(value):
            return False
        if self.scale is AxisScale.LOG10 and value <= 0.0:
            return False
        low, high = self.transform(self.minimum), self.transform(self.maximum)
        slack = _FRAME_SLACK * (high - low)
        return low - slack <= self.transform(value) <= high + slack

    def to_dict(self) -> dict[str, Any]:
        return {
            "minimum": self.minimum,
            "maximum": self.maximum,
            "unit": self.unit,
            "scale": self.scale.value,
        }


@dataclass(frozen=True)
class DigitizedSeries:
    """One curve read off one figure panel, with everything needed to judge it as a reading."""

    #: The claim these values are the reference for. The pairing is the curator's: no rule here
    #: decides that the upper curve of Figure 3A is the plasma claim rather than the liver one.
    claim_id: str
    figure: str
    curve: str
    digitizer: str
    x_axis: Axis
    y_axis: Axis
    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        for field_name in ("claim_id", "figure", "curve", "digitizer"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"a digitized series must state its {field_name.replace('_', ' ')}")
        if len(self.points) < 2:
            raise ValueError(
                f"'{self.curve}' has {len(self.points)} point(s); a curve needs at least two"
            )
        previous: float | None = None
        for x, y in self.points:
            if not self.x_axis.contains(x):
                raise ValueError(
                    f"'{self.curve}' reads x={x} {self.x_axis.unit}, outside its own axis "
                    f"[{self.x_axis.minimum}, {self.x_axis.maximum}] — the calibration is wrong, "
                    "not the curve"
                )
            if not self.y_axis.contains(y):
                raise ValueError(
                    f"'{self.curve}' reads y={y} {self.y_axis.unit}, outside its own axis "
                    f"[{self.y_axis.minimum}, {self.y_axis.maximum}] — the calibration is wrong, "
                    "not the curve"
                )
            if previous is not None and x <= previous:
                raise ValueError(
                    f"'{self.curve}' reads x={x} after x={previous}; the points must increase "
                    "along the axis, and two readings at one x are two values for one place"
                )
            previous = x

    @property
    def span(self) -> tuple[float, float]:
        """The x range actually read — outside it there is no reference, only extrapolation."""
        return self.points[0][0], self.points[-1][0]

    @property
    def source_location(self) -> str:
        """Where these numbers came from, in the form a claim cites its source."""
        return f"{self.figure}, {self.curve} (digitized from the figure with {self.digitizer})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim_id,
            "figure": self.figure,
            "curve": self.curve,
            "digitizer": self.digitizer,
            "x_axis": self.x_axis.to_dict(),
            "y_axis": self.y_axis.to_dict(),
            "points": [[x, y] for x, y in self.points],
        }


def _axis(record: Mapping[str, Any], which: str) -> Axis:
    axis = record.get(which)
    if not isinstance(axis, Mapping):
        raise ValueError(f"the figure states no {which}: every reading needs its axes")
    missing = [key for key in ("minimum", "maximum", "unit") if key not in axis]
    if missing:
        raise ValueError(f"the {which} states no {', '.join(missing)}")
    blank = [
        key for key in ("minimum", "maximum")
        if axis[key] is None or isinstance(axis[key], str) and not axis[key].strip()
    ]
    if blank:
        # A template arrives with these blank, and `float(None)` from inside the reader is the
        # shape this repository already fixed once in the claims loader: the ordinary mistake
        # surfacing as a TypeError with no statement of which line to go and write.
        raise ValueError(f"the {which} states no {', '.join(blank)}: it has not been filled in yet")
    try:
        scale = AxisScale(str(axis.get("scale", "linear")))
    except ValueError:
        raise ValueError(
            f"the {which} is drawn '{axis.get('scale')}'; this reader knows "
            f"{', '.join(s.value for s in AxisScale)}"
        ) from None
    return Axis(
        minimum=float(axis["minimum"]),
        maximum=float(axis["maximum"]),
        unit=str(axis["unit"]),
        scale=scale,
    )


def _pair(point: Any) -> tuple[float, float]:
    """One [x, y] point, refusing anything longer rather than reading past it."""
    if isinstance(point, (str, bytes)) or len(point) != 2:
        raise ValueError("a point is exactly two numbers")
    return float(point[0]), float(point[1])


def read_digitized_figure(text: str) -> tuple[DigitizedSeries, ...]:
    """Read a curator's digitization of one figure panel; raise on anything it cannot trust.

    One file is one panel: the axes are stated once and every series in it was read off them,
    which is what a panel means. A file holding curves from two panels is two files.
    """
    try:
        record = json.loads(text)
    except json.JSONDecodeError as malformed:
        raise ValueError(f"the digitization is not JSON: {malformed}") from None
    if not isinstance(record, Mapping):
        raise ValueError("the digitization must be an object naming a figure and its series")
    figure = str(record.get("figure", "")).strip()
    digitizer = str(record.get("digitizer", "")).strip()
    if not figure or not digitizer:
        raise ValueError(
            "a digitization must name the 'figure' it was read off and the 'digitizer' that read "
            "it; a value with no provenance is not a reference"
        )
    x_axis, y_axis = _axis(record, "x_axis"), _axis(record, "y_axis")
    series = record.get("series")
    if not isinstance(series, Sequence) or isinstance(series, str) or not series:
        raise ValueError(f"{figure} carries no 'series': there is nothing to read")

    read: list[DigitizedSeries] = []
    for entry in series:
        if not isinstance(entry, Mapping):
            raise ValueError(f"{figure} holds a series that is not an object")
        points = entry.get("points")
        if not isinstance(points, Sequence) or isinstance(points, str):
            raise ValueError(f"{figure}'s series '{entry.get('curve', '?')}' carries no points")
        try:
            # Length-checked rather than indexed past: a three-number point is a digitizer writing
            # something this reader does not understand — an error bar, a second series, a label —
            # and taking its first two silently is how a reference gets built out of the wrong
            # column with nothing to show for it.
            pairs = tuple(_pair(p) for p in points)
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValueError(
                f"{figure}'s series '{entry.get('curve', '?')}' has a point that is not an "
                "[x, y] pair of numbers"
            ) from None
        read.append(DigitizedSeries(
            claim_id=str(entry.get("claim", "")),
            figure=figure,
            curve=str(entry.get("curve", "")),
            digitizer=digitizer,
            x_axis=x_axis,
            y_axis=y_axis,
            points=pairs,
        ))
    paired = [s.claim_id for s in read]
    duplicated = sorted({c for c in paired if paired.count(c) > 1})
    if duplicated:
        raise ValueError(
            f"{figure} pairs more than one curve with claim(s) {', '.join(duplicated)}: which "
            "curve the claim reads is the curator's statement, and two of them is not one"
        )
    return tuple(read)


def series_resolution(series: DigitizedSeries) -> dict[str, Any]:
    """How finely the curve was read: the count, the span, and the widest gap it was read over.

    The widest gap is the number that matters, and it is reported rather than judged. Between two
    read points the reference is a straight line in the axis's scale, so a gap covering a third of
    the span means a third of the comparison is against the curator's interpolation and not
    against the figure.
    """
    low, high = series.span
    xs = [series.x_axis.transform(x) for x, _ in series.points]
    width = xs[-1] - xs[0]
    gap = max(b - a for a, b in zip(xs, xs[1:]))
    return {
        "points": len(series.points),
        "span": [low, high],
        "widest_gap": gap,
        "widest_gap_fraction": gap / width if width > 0 else float("nan"),
    }


def resample_series(series: DigitizedSeries, times: Sequence[float]) -> tuple[float, ...]:
    """The digitized curve on the run's own sample grid, interpolated in the axes' own scales.

    Raises rather than extrapolate: a time outside the digitized span has no reference behind it,
    and returning the last read value there would compare the model against the edge of a picture.
    """
    # Materialized for the same reason the claims are: the grid is walked twice, to check it and
    # to sample it, and a caller passing an iterator would have it consumed by the check.
    times = tuple(times)
    if not times:
        raise ValueError(
            f"'{series.curve}' was asked for no samples: a claim resampled onto an empty grid "
            "gets no reference, which is indistinguishable from never having been digitized"
        )
    low, high = series.span
    for t in times:
        if not math.isfinite(t) or t < low or t > high:
            raise ValueError(
                f"'{series.curve}' was read over [{low}, {high}] {series.x_axis.unit} and cannot "
                f"be resampled at {t}: outside that span there is no reading, only extrapolation"
            )
    xs = [series.x_axis.transform(x) for x, _ in series.points]
    ys = [series.y_axis.transform(y) for _, y in series.points]

    resampled: list[float] = []
    for t in times:
        target = series.x_axis.transform(t)
        index = 0
        while index < len(xs) - 2 and xs[index + 1] < target:
            index += 1
        left, right = xs[index], xs[index + 1]
        weight = 0.0 if right == left else (target - left) / (right - left)
        resampled.append(series.y_axis.untransform(ys[index] + weight * (ys[index + 1] - ys[index])))
    return tuple(resampled)


def curve_reference(series: DigitizedSeries, *, duration: float, steps: int) -> tuple[float, ...]:
    """The digitized curve on the grid a ``duration``/``steps`` run is sampled at.

    A curve claim is judged point against point, so the reference must sit on the run's own
    ``steps + 1`` uniform samples over ``[0, duration]``. Sampling it anywhere else is a defect the
    oracle can only see as a length mismatch, and this is the one place that grid is derived from
    the same two numbers the claim already states. A window the curator did not read over raises
    here rather than being padded.
    """
    if steps < 1:
        raise ValueError(f"a run of {steps} steps samples no interval to compare over")
    if duration <= 0.0:
        # A window of zero returns the initial condition at every sample, and a curve judged over
        # it reproduces perfectly by construction — the shape `certify_curves` records its protocol
        # to make visible, refused here rather than published.
        raise ValueError(
            f"a window of {duration} has no curve in it: every sample is the initial condition, "
            "and a comparison over it passes whatever the model does"
        )
    return resample_series(series, [duration * i / steps for i in range(steps + 1)])


def pairing_faults(
    claims: Iterable[DossierClaim],
    series: Iterable[DigitizedSeries],
    *,
    carrier: str = "this dossier",
) -> tuple[str, ...]:
    """Every way this digitization is paired with the wrong claims, named one per fault.

    The pairing is the curator's statement and the one part of the file nobody can guess, so it is
    also the part a typo, a renamed output, or a digitization read against an older document
    breaks silently. These three faults were reachable only from :func:`attach_digitized_values`,
    which is to say only from Python: a curator working at the terminal wrote the pairing, filled
    in the reading, and was told nothing until somebody else ran the join. They live here so the
    way in and the way out cannot disagree about what a bad pairing is.

    ``carrier`` names what the claims came from, because the same fault reads differently to the
    two callers: a dossier this repository ingested, or the author's own document.

    All of them are reported, never the first one only. A curator fixing one id at a time learns
    nothing about the other four.
    """
    claims, series = tuple(claims), tuple(series)
    by_claim = {s.claim_id: s for s in series}
    known = {claim.id for claim in claims}
    faults: list[str] = []
    unpaired = sorted(set(by_claim) - known)
    if unpaired:
        faults.append(
            f"the digitization names claim(s) {', '.join(unpaired)}, which {carrier} does not "
            "carry: a reading paired with nothing is a reading of the wrong figure"
        )
    for claim in claims:
        if claim.id not in by_claim:
            continue
        if not claim.targetable:
            faults.append(
                f"claim '{claim.id}' is retained non-targetable, and giving it values would "
                "promote it into a result the paper never staked; that is a tracked revision"
            )
        elif claim.reference_data:
            faults.append(
                f"claim '{claim.id}' already carries {len(claim.reference_data)} reference "
                "value(s); a reading off the picture does not replace numbers the paper shipped"
            )
    return tuple(faults)


def window_faults(
    series: Iterable[DigitizedSeries],
    windows: Sequence[tuple[float, float]],
    *,
    carrier: str = "this dossier",
) -> tuple[str, ...]:
    """Every reading that does not cover a window the document actually runs.

    Nothing is extrapolated: a claim is judged on the run's own samples, and a sample past either
    end of what the curator read raises rather than being padded with the nearest value. That
    refusal is right and it arrives late — at the join, in Python, after the curator has finished.
    A reading that starts at 0.5 h against a run that starts at 0 is a file that is internally
    perfect and cannot be used, and the two numbers that say so are both on disk while the curator
    is still at the terminal.

    A series covering *any* of the windows is not reported: a document running several time courses
    is one figure per window, and the curator read one of them.

    Windows are compared as numbers, because that is all either file states. A figure read in hours
    against a model whose time is in minutes fails here — and it fails at the join too, for the same
    reason, so naming it is the earliest this repository can say it.
    """
    faults = []
    stated = ", ".join(f"{start:g}-{end:g}" for start, end in windows)
    for reading in series:
        xs = [x for x, _ in reading.points]
        low, high = min(xs), max(xs)
        if any(low <= start and high >= end for start, end in windows):
            continue
        faults.append(
            f"series '{reading.claim_id}' was read over {low:g}-{high:g} "
            f"{reading.x_axis.unit}, and {carrier} runs {stated}: a claim judged over that window "
            "needs values outside what was read, and nothing here is extrapolated"
        )
    return tuple(faults)


def attach_digitized_values(
    claims: Iterable[DossierClaim],
    series: Iterable[DigitizedSeries],
    *,
    times: Sequence[float],
) -> tuple[DossierClaim, ...]:
    """Give each paired claim the curve read off its figure, on the grid ``times`` samples.

    A claim with no series is returned untouched — still figure-referenced, still abstaining —
    because a partial digitization is a partial digitization and not a reason to guess the rest.
    The reference kind is always ``digitized-figure``: a value read off a picture cannot be
    recorded as a printed number, so the wider band it is judged in is not escapable from here.
    """
    # Both are read twice — once to check the pairing, once to apply it — so a caller passing a
    # generator would otherwise have its claims consumed by the check and get an empty result.
    claims, series = tuple(claims), tuple(series)
    faults = pairing_faults(claims, series)
    if faults:
        raise ValueError("; ".join(faults))
    by_claim = {s.claim_id: s for s in series}

    attached: list[DossierClaim] = []
    for claim in claims:
        reading = by_claim.get(claim.id)
        if reading is None:
            attached.append(claim)
            continue
        attached.append(DossierClaim(
            id=claim.id,
            quantity=claim.quantity,
            conditions=claim.conditions,
            source_location=f"{claim.source_location}; values from {reading.source_location}",
            targetable=True,
            reference_kind=ReferenceKind.DIGITIZED_FIGURE,
            reference_data=resample_series(reading, times),
        ))
    return tuple(attached)


#: The fields a template leaves for the curator, in the order the file lists them.
_FILL_IN = (
    ("figure", "which figure and panel you read"),
    ("digitizer", "the tool that read it, with its version"),
)


def figure_template(sedml: str) -> dict[str, Any]:
    """A digitization file for the curves a document plots, with the claim pairing filled in.

    The pairing is the one mechanical part of this file and the one nobody can guess: a claim id
    read off a SED-ML document is ``plot_0__plot_0_0_0__plot_0_0_1``, it has to match exactly, and
    a digitization paired with an id the dossier does not carry is refused. So the template writes
    the ids and the curve each one plots, and leaves everything that is a *reading* blank — the
    figure, the tool, both axis ranges, and every point. None of those can be derived from a
    document, and a template that filled in an axis range would be stating what a picture shows.

    A curve the document already ships values for gets no stub, with the reason: those are the
    paper's own recorded points, and a reading of a picture of them is a downgrade.
    """
    from .sedml import enumerate_sedml_claims

    claims = enumerate_sedml_claims(sedml)
    series, notes = [], []
    for claim in claims:
        if not claim.targetable:
            continue
        if claim.reference_data:
            notes.append(
                f"'{claim.id}' ({claim.quantity}) already carries the values your document ships, "
                "so it needs no reading: a digitization of a picture of them would replace your "
                "own recorded points"
            )
            continue
        series.append({"claim": claim.id, "curve": claim.quantity, "points": []})
    if not series:
        notes.append(
            "this document plots no curve that needs a reading, so there is nothing to digitize"
        )
    return {
        "figure": "",
        "digitizer": "",
        "x_axis": {"minimum": None, "maximum": None, "unit": ""},
        "y_axis": {"minimum": None, "maximum": None, "unit": "", "scale": "linear"},
        "series": series,
        "notes": notes,
    }


def unfilled_figure(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Which of a template's blanks are still blank, named one per line.

    A template handed straight back is the ordinary mistake. Reading it would refuse on whichever
    blank it happened to reach first, which says nothing about the other four; this says what is
    left to write.
    """
    unfilled = [
        f"'{field}' is blank — {what}"
        for field, what in _FILL_IN
        if not str(record.get(field) or "").strip()
    ]
    for which in ("x_axis", "y_axis"):
        axis = record.get(which)
        if not isinstance(axis, Mapping):
            unfilled.append(f"'{which}' is missing — the range and unit the curve was read against")
            continue
        for key in ("minimum", "maximum"):
            value = axis.get(key)
            if value is None or isinstance(value, str) and not value.strip():
                unfilled.append(f"'{which}.{key}' is blank — where that end of the axis sits")
        if not str(axis.get("unit") or "").strip():
            unfilled.append(f"'{which}.unit' is blank — what the axis measures")
    for entry in record.get("series") or ():
        if isinstance(entry, Mapping) and not (entry.get("points") or ()):
            unfilled.append(
                f"'{entry.get('claim', '?')}' has no points — the curve has not been read yet"
            )
    return tuple(unfilled)


__all__ = [
    "Axis",
    "AxisScale",
    "DigitizedSeries",
    "attach_digitized_values",
    "curve_reference",
    "figure_template",
    "pairing_faults",
    "read_digitized_figure",
    "resample_series",
    "series_resolution",
    "unfilled_figure",
    "window_faults",
]
