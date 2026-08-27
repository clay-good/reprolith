"""The registry page is built from text a paper supplied, so it is tested with hostile text.

`render_registry` and `render_badge` interpolate paper titles, model classes, and identifiers into
HTML and SVG. Every interpolation escapes today — the point of this file is that nothing checked,
and an escape dropped in a later edit would produce a published page that renders wrong at best and
executes at worst. Reprolith's whole output is artifacts other people open.

Pure stdlib, so it runs on the dependency-free core gate.
"""

from __future__ import annotations

from html.parser import HTMLParser

from reprolith import (
    Certificate,
    ClaimAssessment,
    EnginePin,
    PaperIdentity,
    Verdict,
    build_certificate,
    render_badge,
    render_registry,
)

#: One string carrying every character that breaks out of a different HTML context: a tag, an
#: attribute value in double and single quotes, and an entity.
_HOSTILE = '<script>alert("x")</script> & \'quoted\' <img src=x onerror=y>'


def _certificate(title: str) -> Certificate:
    return build_certificate(
        paper=PaperIdentity(title=title, doi=_HOSTILE, pubmed_id=_HOSTILE),
        engine_pin=EnginePin(engine="copasi", version="4.46"),
        assessments=[ClaimAssessment(
            claim_id="C1", quantity=_HOSTILE, verdict=Verdict.REPRODUCED,
            source_location=_HOSTILE,
        )],
    )


#: Tags that never carry a closing tag in HTML. SVG's self-closing elements are not here: they are
#: written `<rect …/>`, which `HTMLParser` reports through `handle_startendtag` and which this
#: therefore never puts on the stack. Treating them as void in only one of the two handlers is how
#: the first version of this parser reported the *page* as unbalanced when it was the parser.
_VOID = {"meta", "br", "hr", "img", "input", "link"}


class _Balance(HTMLParser):
    """Enough of a parser to catch a tag opened by injected text or left unclosed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.problems: list[str] = []
        self.saw: set[str] = set()

    def handle_startendtag(self, tag: str, attrs: object) -> None:
        self.saw.add(tag)  # `<rect/>` opens and closes itself; it never reaches the stack

    def handle_starttag(self, tag: str, attrs: object) -> None:
        self.saw.add(tag)
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID:
            return
        if not self.stack:
            self.problems.append(f"</{tag}> with nothing open")
        elif self.stack[-1] != tag:
            self.problems.append(f"</{tag}> closes <{self.stack[-1]}>")
            self.stack.pop()
        else:
            self.stack.pop()


def test_a_hostile_title_never_becomes_markup_in_the_registry() -> None:
    page = render_registry([("ode-pkpd", _certificate(_HOSTILE))])
    assert "<script>alert" not in page
    assert "onerror=y>" not in page
    assert "&lt;script&gt;" in page, "the title should appear, escaped, not be dropped"


def test_the_registry_page_stays_well_formed_around_hostile_text() -> None:
    """Escaping is only half of it: a page whose tags no longer balance renders unpredictably, and
    a reader cannot tell a mangled card from an honest one."""
    page = render_registry([("ode-pkpd", _certificate(_HOSTILE))])
    parser = _Balance()
    parser.feed(page)
    assert not parser.problems, parser.problems
    assert not parser.stack, f"unclosed tags: {parser.stack}"
    assert {"article", "h3", "svg"} <= parser.saw, "the card did not render its usual structure"


def test_the_badge_svg_survives_hostile_text_too() -> None:
    """The badge is embedded into the registry raw — it is markup by construction — so it has to do
    its own escaping. It is also served on its own, on third-party pages."""
    badge = render_badge(_certificate(_HOSTILE))
    assert "<script>alert" not in badge
    parser = _Balance()
    parser.feed(badge)
    assert not parser.problems, parser.problems
    assert not parser.stack, f"unclosed tags: {parser.stack}"


def test_a_hostile_class_name_cannot_escape_a_filter_attribute() -> None:
    """The class name reaches both a `data-class` attribute and a filter button's `data-value`,
    which is the one path where injected text lands inside a quoted attribute rather than a body."""
    page = render_registry([('ode" onmouseover="x', _certificate("ordinary title"))])
    assert 'onmouseover="x' not in page
    parser = _Balance()
    parser.feed(page)
    assert not parser.problems, parser.problems
