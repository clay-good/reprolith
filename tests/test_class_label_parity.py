"""The class a verdict came from, the same on the page and in the terminal.

`ReprolithQuery` carries a digest-to-class map with this comment beside it:

    Same source as the page (`milestone_certificate_dirs`), so the browser and the terminal
    cannot disagree about which class a verdict came from.

The argument is sound and it was never run. `model_classes` is a constructor argument, so what
actually prevents the drift is that both callers happen to derive it from the same function — and
a caller that stopped doing so would leave the comment standing while the two surfaces disagreed.
This repository's own recurring finding is a comment claiming a parity the code does not enforce;
this is the check that makes the comment true rather than plausible.

The class is genuinely outside the certificate — nothing in one says which pathway produced it, and
the page has always labelled its cards from the directory the certificate was found in — so there is
no third source to arbitrate between them. That is exactly why they have to be compared to each
other rather than each to a spec.
"""

from __future__ import annotations

import re
from pathlib import Path

from reprolith.mcp_server import load_repository, milestone_certificate_dirs

_ROOT = Path(__file__).resolve().parents[1]


def _page_labels() -> dict[str, str]:
    """Each published card's digest and the class the page labels it with."""
    page = (_ROOT / "datasets" / "registry.html").read_text(encoding="utf-8")
    labels: dict[str, str] = {}
    for card in page.split('<article class="entry"')[1:]:
        digest = re.search(r"([0-9a-f]{64})", card)
        model_class = re.search(r'data-class="([a-z-]+)"', card)
        if digest and model_class:
            labels[digest.group(1)] = model_class.group(1)
    return labels


def test_the_page_and_the_terminal_agree_on_every_published_verdict() -> None:
    query, _catalog = load_repository(_ROOT / "datasets", aggregate=True)
    page = _page_labels()
    assert page, "the registry page publishes cards with a digest and a class"

    terminal = {
        digest: query.model_class_of(digest)
        for digest in page
    }
    disagreements = {
        digest: (page[digest], terminal[digest])
        for digest in page
        if page[digest] != terminal[digest]
    }
    assert disagreements == {}
    # And the terminal knows about every class the page publishes, so agreement is not agreement
    # about an empty set — the failure mode a label falling through would produce.
    assert set(terminal.values()) == set(milestone_certificate_dirs())
