#!/usr/bin/env python3
"""Measure what stands between the blocked entries and a reading: the figures, as published.

The roadmap has said for months that the remaining entries need "figure digitization", which is
true and useless — it says nothing about which of them is an afternoon's work and which cannot be
read at all. Four figures have now been read and three more were opened and abandoned, and the
difference between them turned out not to be the one everybody assumes.

**It is not panel size.** Zake et al. 2021's panels are 280x257 pixels and all ten were read;
Koeller et al. 2021's are 234x200 and unreadable. What separates them is measurable, and this
script measures it on every figure of every blocked paper this corpus can fetch — seven papers, 10 of the 24 blocked entries, listed in
``scripts/figure_survey_papers.json``:

``frame``
    Whether the panel is drawn as a closed box. The colour trace locates the plotting area by
    finding two long horizontal and two long vertical runs of ink; a figure drawn with L-shaped
    axes has no such thing, and no amount of curator patience substitutes for it. This is the
    obstacle most often mistaken for resolution — and the first thing this survey settled was that
    an earlier version of this very paragraph had the wrong papers in it. It named Dwivedi et al.
    2014 and Demin et al. 2013 as the frameless pair, from memory. Demin's six figures do measure
    as frameless, every one. **Dwivedi's do not**: five of its eight hold a closed box and three of
    those are drawn in two or more separable colours, which makes the four entries behind that one
    paper — the largest single block in the backlog — the strongest remaining candidate rather than
    the dead end the prose had recorded.

``colours``
    How many distinct saturated hues the image holds. A trace separates lines by colour, so this
    is a ceiling on how many series can be told apart. One means the lines are black or grey and
    the dark-line modes are the only way in; zero means there is nothing here a colour trace reads.

``pixels_per_panel``
    Reported because it is the number people reach for, and so that the claim that it is *not* the
    discriminator can be checked rather than believed. Panels are counted from the image's own
    caption label, not guessed from the picture.

What it cannot see is the third obstacle, and the output says so: whether the *curve* is resolvable
in the panel it is drawn in. Koeller's intravenous bolus puts its whole rise — a hundred and ninety
pixels of the y axis — inside one pixel of x, and no property of the image says that; it takes the
model, or an eye. The entries where that is the finding carry it as a note here rather than a
measurement.

Each paper also carries its ``license`` as Europe PMC states it, and the file ends with a
``summary``: how many figures answered, how many hold a plotting box, how many of those are
separable by colour, and which papers were unreachable or carried forward from an earlier run. The
licence decides *how* a figure would be redistributed rather than whether it can be read — under a
no-derivatives licence the image file is committed in the publisher's own bytes — and it is here so
that call is made before an afternoon goes into the reading.

Dev-only and network-bound, like the other ``survey_*`` scripts. Needs Pillow and numpy. It writes
``datasets/manuscripts/figure_survey.json``, which is what the test reads.

    python scripts/survey_published_figures.py
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import numpy as np  # noqa: E402
from PIL.Image import open as decode_image  # noqa: E402

#: Europe PMC serves a paper's figure images in one zip, which is the only route that works for
#: every publisher here: the direct `/bin/` paths 403, and the per-journal CDN layouts differ.
_SUPPLEMENTARY = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"
#: The same service states each paper's licence, which decides not *whether* a figure can be read
#: but how: a no-derivatives licence is redistributed in the publisher's own bytes, unmodified.
_METADATA = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    "?query=PMCID:{pmcid}&resultType=core&format=json&pageSize=1"
)

#: A pixel this far from grey carries a hue. The same span the digitizer's own `_ink` uses to call
#: a pixel colourless, so "how many colours are here" is counted the way the trace counts them.
_SATURATION = 60
#: Hues this close together are one colour for the purpose of telling two lines apart.
_HUE_BUCKETS = 24
#: A bucket holding fewer pixels than this is an artefact of the encoder, not a line.
_MIN_HUE_PIXELS = 200
#: A run of ink this long, as a share of the image's own width or height, is an axis or a frame.
_FRAME_SHARE = 0.55


def _fetch(pmcid: str) -> dict[str, bytes]:
    """Every image in the paper's supplementary bundle, by filename."""
    with urllib.request.urlopen(_SUPPLEMENTARY.format(pmcid=pmcid), timeout=120) as response:
        payload = response.read()
    images: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        for name in bundle.namelist():
            if name.lower().endswith((".jpg", ".jpeg", ".png")):
                images[name] = bundle.read(name)
    return images


def _licence(pmcid: str) -> str:
    """The paper's licence as Europe PMC states it, or "" when it states none.

    What it decides is narrower than it looks. A no-derivatives licence does not stop a figure
    being read — Benson et al. 2014 is CC BY-NC-ND and six of its curves are on a published
    certificate — but it does decide that the image is redistributed in the publisher's own bytes,
    so a curator must not re-encode or crop the file itself. Recorded here so that decision is
    made before an afternoon goes into the reading, not after.
    """
    with urllib.request.urlopen(_METADATA.format(pmcid=pmcid), timeout=60) as response:
        answer = json.loads(response.read().decode("utf-8"))
    results = answer.get("resultList", {}).get("result", [])
    return str(results[0].get("license", "")) if results else ""


def _ink(rgb: np.ndarray) -> np.ndarray:
    grey = rgb.mean(axis=2)
    colourless = (rgb.max(axis=2) - rgb.min(axis=2)) < 40
    return np.where(colourless, (255.0 - grey) / 255.0, 0.0)


def _closed_frame(rgb: np.ndarray) -> bool:
    """Whether the image holds two long horizontal and two long vertical runs of ink.

    The same shape `scripts/digitize_figure_panels.py` looks for, asked of the whole image rather
    than of a stated crop: a figure with no such pair anywhere has no panel the colour trace can
    locate, whatever a curator does with it.
    """
    ink = _ink(rgb)
    height, width = ink.shape
    rows = int((ink.sum(axis=1) > _FRAME_SHARE * width * 0.5).sum())
    columns = int((ink.sum(axis=0) > _FRAME_SHARE * height * 0.5).sum())
    return rows >= 2 and columns >= 2


def _distinct_colours(rgb: np.ndarray) -> int:
    """How many saturated hues the image holds, bucketed coarsely enough to be lines not noise."""
    saturated = (rgb.max(axis=2) - rgb.min(axis=2)) > _SATURATION
    if not saturated.any():
        return 0
    pixels = rgb[saturated].astype(float)
    high, low = pixels.max(axis=1), pixels.min(axis=1)
    span = np.where(high - low == 0, 1.0, high - low)
    red, green, blue = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    hue = np.where(
        high == red, (green - blue) / span % 6,
        np.where(high == green, (blue - red) / span + 2, (red - green) / span + 4),
    ) / 6.0
    counts = np.bincount((hue * _HUE_BUCKETS).astype(int) % _HUE_BUCKETS, minlength=_HUE_BUCKETS)
    return int((counts >= _MIN_HUE_PIXELS).sum())


def _summarise(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """The conclusion the per-figure measurements add up to, so a reader need not recompute it.

    Three numbers, in the order a curator uses them: how many figures answered at all, how many
    hold a plotting box the trace can locate, and how many of those are drawn in two or more
    separable colours. The last is the count of candidates to open — the figures where neither
    obstacle this script *can* see is in the way.
    """
    figures = [figure for entry in entries for figure in entry.get("figures", ())]
    framed = [figure for figure in figures if figure["frame"]]
    return {
        "measured": len(figures),
        "with_closed_frame": len(framed),
        "framed_and_separable_by_colour": sum(1 for f in framed if f["colours"] >= 2),
        "unreachable": sorted(e["pmcid"] for e in entries if "error" in e),
        "carried_from_an_earlier_run": sorted(e["pmcid"] for e in entries if "carried_from" in e),
    }


def survey(
    papers: dict[str, dict[str, Any]], previous: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Measure every figure of every paper, carrying forward what this run could not reach.

    `previous` is the committed survey's papers, by pmcid. A paper that answers with an error here
    keeps the figures an earlier run measured, stamped with `carried_from` so the row says it was
    not measured now — without that, a rate-limited afternoon would delete a measurement nobody
    can retake on demand. A paper that answers keeps nothing: this run's numbers are this build's.
    """
    carried = previous or {}
    entries = []
    for pmcid, about in sorted(papers.items()):
        try:
            licence = _licence(pmcid)
        except Exception:  # noqa: BLE001 - an unstated licence is recorded as unstated
            licence = carried.get(pmcid, {}).get("license", "")
        about = {**about, "license": licence}
        try:
            images = _fetch(pmcid)
        except Exception as unreachable:  # noqa: BLE001 - a survey records what it could not read
            entry = {"pmcid": pmcid, **about, "error": str(unreachable)}
            earlier = carried.get(pmcid, {}).get("figures")
            if earlier:
                entry["figures"] = earlier
                entry["carried_from"] = (
                    "an earlier run; this one reached " + str(unreachable)
                )
            entries.append(entry)
            continue
        figures = []
        for name, payload in sorted(images.items()):
            try:
                with decode_image(io.BytesIO(payload)) as picture:
                    rgb = np.asarray(picture.convert("RGB"))
            except Exception:  # noqa: BLE001 - a file that is not an image is not a figure
                continue
            height, width = rgb.shape[:2]
            panels = int(about.get("panels", {}).get(name, 1))
            figures.append({
                "file": name,
                "width": width,
                "height": height,
                "panels": panels,
                "pixels_per_panel": round(width * height / max(panels, 1)),
                "frame": _closed_frame(rgb),
                "colours": _distinct_colours(rgb),
            })
        entries.append({"pmcid": pmcid, **about, "figures": figures})
    return {
        "description": (
            "What the blocked entries' figures are, as published. Regenerate with "
            "scripts/survey_published_figures.py. `frame` is whether the image holds a closed "
            "plotting box, which is what the colour trace locates a panel by; `colours` is how "
            "many saturated hues it holds, which is a ceiling on how many series can be told "
            "apart; `pixels_per_panel` is reported so the common belief that size is the obstacle "
            "can be checked against the figures already read."
        ),
        "limits": [
            "Panel counts are the paper's own labels where this file states them and 1 otherwise, "
            "so `pixels_per_panel` is an upper bound for a multi-panel image nobody has counted.",
            "A closed frame is necessary and not sufficient: the third obstacle is whether the "
            "curve is resolvable in the panel it is drawn in, which no property of the image "
            "shows. Koeller et al. 2021's bolus puts a hundred and ninety pixels of y range "
            "inside one pixel of x, and a figure like that measures as readable here. So a "
            "figure counted as framed and coloured is a candidate to open, never a certainty.",
            "Only figures the supplementary bundle carries are measured. A paper whose images are "
            "served only from a publisher's own CDN is recorded with the error that reached it.",
            "`license` is what Europe PMC states for the paper, and it decides how a figure is "
            "redistributed rather than whether it can be read: under a no-derivatives licence "
            "the image file is committed in the publisher's own bytes, un-re-encoded and "
            "un-cropped. An empty string means the service stated none, which is a question for "
            "the publisher's page and not a permission.",
            "The bundle is not the same on two calls. Runs minutes apart returned 51 images, "
            "then 44, then none at all over the same seven papers, and one paper answered with "
            "a 500 in the first and eight figures in the second — so a figure count here is a "
            "floor on what the paper has, never a census, and the properties measured per "
            "figure are what this file is for. A paper that errored and had never been measured "
            "contributed nothing to the counts; one measured by an earlier run keeps those "
            "figures and says so in `carried_from`, so its numbers are an earlier build's.",
        ],
        "summary": _summarise(entries),
        "papers": entries,
    }


def main() -> int:
    papers = json.loads(
        (REPO / "scripts" / "figure_survey_papers.json").read_text(encoding="utf-8")
    )
    out = REPO / "datasets" / "manuscripts" / "figure_survey.json"
    previous: dict[str, dict[str, Any]] = {}
    if out.exists():
        previous = {
            paper["pmcid"]: paper
            for paper in json.loads(out.read_text(encoding="utf-8"))["papers"]
        }
    result = survey(papers, previous)
    measured_now = sum(len(paper.get("figures", ())) for paper in result["papers"])
    if out.exists():
        # A survey of a flaky source must not replace a measurement with the network's bad day.
        # Measured while writing this: three runs minutes apart returned 51 figures, then 44, then
        # **nothing at all** — every paper a 503 — and the third silently overwrote the second.
        # A committed file that quietly got emptier is the shape this repository refuses
        # everywhere else, and a survey script is no exception.
        before = sum(len(paper.get("figures", ())) for paper in previous.values())
        if measured_now < before and "--force" not in sys.argv:
            print(
                f"refusing to overwrite: {out.relative_to(REPO)} holds {before} measured "
                f"figure(s) and this run has {measured_now}. A paper that errored keeps the "
                "figures an earlier run measured, so this means a paper that *answered* served "
                "fewer images than before — the endpoint rate-limits and truncates under it. Run "
                "it again later, or pass --force if the smaller result is the one you mean."
            )
            return 1
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    measured = [f for paper in result["papers"] for f in paper.get("figures", ())]
    framed = [f for f in measured if f["frame"]]
    print(f"wrote {out.relative_to(REPO)} — {len(measured)} figure(s) across {len(papers)} paper(s)")
    print(f"  with a closed plotting box: {len(framed)}")
    print(f"  with two or more separable colours: {sum(1 for f in framed if f['colours'] >= 2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
