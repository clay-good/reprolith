"""The published page's text is readable, measured rather than eyeballed.

`datasets/registry.html` is the one artifact in this repository written to be *looked at* — the
public list of what reproduced and what did not. Its verdict words are the most-read text on it,
and three of them did not meet the contrast a reader needs: a green at 3.03:1 against white where
4.5:1 is the bar, an amber at 3.37:1, and the digest line at 3.54:1. The `blocked` grey sat at
4.48:1, which is the near-miss nobody notices and everybody squints at.

Held here rather than in the renderer's docstring for the reason every other count on this
repository is held by a test: a colour someone nudges later reads fine to the person who nudged
it. Pure stdlib, so it runs on the dependency-free core gate.
"""

from __future__ import annotations

import re
from pathlib import Path

_PAGE = (Path(__file__).parent.parent / "datasets" / "registry.html").read_text(encoding="utf-8")
#: WCAG AA for body text. The page sets nothing large enough to qualify for the 3:1 exception —
#: its biggest text is a heading, and a heading that fails is no more readable than a paragraph.
_AA = 4.5
#: The darkest surface any of this page's text sits on. Checking every colour against it is the
#: conservative reading: a lighter background would only flatter the numbers.
_DARKEST_SURFACE = "#f6f6f6"
#: The one inverted pair: a selected filter chip is white on near-black, and reading it against
#: the page's own surface would measure a combination that never appears.
_INVERTED = ("#fff", "#222")


def _luminance(colour: str) -> float:
    value = colour.lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    channels = []
    for pair in (value[0:2], value[2:4], value[4:6]):
        part = int(pair, 16) / 255
        channels.append(part / 12.92 if part <= 0.03928 else ((part + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _stylesheet() -> str:
    style = re.search(r"<style>(.*?)</style>", _PAGE, re.S)
    assert style is not None, "the registry page has no stylesheet; this check would pass vacuously"
    return style.group(1)


def test_every_colour_the_page_sets_is_readable_on_the_surface_it_sits_on() -> None:
    colours = set(re.findall(r"color:(#[0-9a-fA-F]{3,6})", _stylesheet()))
    assert len(colours) > 5, colours
    for colour in sorted(colours):
        if colour.lower() == _INVERTED[0]:
            assert _contrast(*_INVERTED) >= _AA, _INVERTED
            continue
        measured = _contrast(colour, _DARKEST_SURFACE)
        assert measured >= _AA, f"{colour} is {measured:.2f}:1 on {_DARKEST_SURFACE}, under {_AA}"


def test_the_verdict_words_are_the_ones_this_most_protects() -> None:
    """Named, because they are what a reader came for and what the page repeats forty-one times."""
    style = _stylesheet()
    for verdict in ("reproduced", "partially-reproduced", "not-reproduced", "blocked"):
        found = re.search(rf"\.v-{re.escape(verdict)}{{color:(#[0-9a-fA-F]{{3,6}})}}", style)
        assert found is not None, verdict
        measured = _contrast(found.group(1), _DARKEST_SURFACE)
        assert measured >= _AA, f"{verdict} is {measured:.2f}:1"


def test_the_heading_sizes_step_rather_than_sit_flat() -> None:
    """Browser defaults put h3 at 1.17x body, which is too small a step to read as one.

    A card's title and the sentence under it looked like the same thing, which on a page of forty
    cards is the difference between scanning and reading.
    """
    style = _stylesheet()
    sizes = {}
    for role in ("h1", "h2", "h3"):
        found = re.search(rf"{role}{{font-size:([0-9.]+)rem", style)
        assert found is not None, role
        sizes[role] = float(found.group(1))
    steps = [sizes["h1"] / sizes["h2"], sizes["h2"] / sizes["h3"], sizes["h3"] / 1.0]
    for step in steps:
        assert step >= 1.25, sizes
