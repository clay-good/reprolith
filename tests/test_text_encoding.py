"""No file is read or written at the machine's preferred encoding.

The defect this exists for: `Path.read_text()` with no `encoding` decodes at whatever
`locale.getpreferredencoding()` says, and CI's Linux runners say **ASCII**. A test that passes on
every developer machine then fails on the one that matters, with a `UnicodeDecodeError` from inside
a model file whose only sin is an en dash. It has now happened twice.

The local gates cannot reproduce it — macOS reports UTF-8 even under `LC_ALL=C`, so the
dependency-free run that exists to catch exactly this class of drift is structurally blind to it.
So the rule is checked statically instead, which needs no locale at all.

Binary reads are untouched: `read_bytes`, and `open` in a mode containing `b`, carry no encoding by
definition. So is an encoding passed positionally — `read_text("utf-8")` is six existing calls in
this repository, and a check that reported them would have sent someone to "fix" code that already
does the right thing, which is the failure mode this whole file is guarding against one level up.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_TREES = ("python", "tests", "scripts")

#: Calls whose text encoding is the machine's unless it is given, and which positional argument
#: carries it. ``Path.read_text(encoding, errors)`` takes it first and ``Path.write_text(data,
#: encoding)`` second; ``open`` is only ever written with the keyword, so it has no position.
_TEXT_CALLS = {"read_text": 0, "write_text": 1, "open": None}


def _is_binary(call: ast.Call) -> bool:
    """An `open(..., "rb")` — positional or keyword — carries no encoding by definition."""
    modes = [a for a in call.args[1:2]] + [
        kw.value for kw in call.keywords if kw.arg == "mode"
    ]
    return any(isinstance(m, ast.Constant) and "b" in str(m.value) for m in modes)


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr if isinstance(node.func, ast.Attribute)
            else node.func.id if isinstance(node.func, ast.Name)
            else ""
        )
        if name not in _TEXT_CALLS or _is_binary(node):
            continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        position = _TEXT_CALLS[name]
        if position is not None and len(node.args) > position:
            continue
        found.append(f"{path.relative_to(_ROOT)}:{node.lineno} {name}() with no encoding")
    return found


def test_no_text_read_or_write_uses_the_machines_preferred_encoding() -> None:
    files = sorted(
        path
        for tree in _TREES
        for path in (_ROOT / tree).rglob("*.py")
        if "__pycache__" not in path.parts
    )
    assert len(files) > 50, "the sweep must actually reach this repository's sources"
    offenders = [line for path in files for line in _offenders(path)]
    assert offenders == [], (
        "these decode at the machine's preferred encoding, which is ASCII on CI:\n  "
        + "\n  ".join(offenders)
    )


def test_the_sweep_would_catch_one() -> None:
    """Without this the assertion above passes for a sweep that parses nothing."""
    sample = _ROOT / "tests" / "test_text_encoding.py"
    tree = ast.parse('from pathlib import Path\nPath("x").read_text()\n')
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call))
    assert not any(kw.arg == "encoding" for kw in call.keywords)
    assert not call.args, "the sample must be the bare call the sweep has to catch"
    assert _offenders(sample) == [], "this file must itself obey the rule it enforces"
