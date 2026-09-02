"""Every name this repository's documentation imports from itself still exists.

`tests/test_documented_commands.py` holds the terminal lines to the real parser. The Python blocks
had nothing: fifteen of them across five documents, each importing from `reprolith` by name, and a
rename would leave every one silently wrong — found by the reader who pasted it.

Parsing is the depth here, as it is there: the names are resolved against the installed package,
not executed. Running them would need the optional extras and, for several, a model file the
document is describing rather than shipping.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BLOCK = re.compile(r"```python\n(.*?)```", re.S)


def _blocks() -> list[tuple[Path, str]]:
    found = [
        (path, block)
        for path in sorted(_REPO.rglob("*.md"))
        if ".venv" not in path.parts
        for block in _BLOCK.findall(path.read_text(encoding="utf-8"))
    ]
    assert found, "no Python blocks found in the documentation; this check would pass vacuously"
    return found


def test_every_documented_block_parses() -> None:
    for path, block in _blocks():
        try:
            ast.parse(block)
        except SyntaxError as broken:
            raise AssertionError(
                f"{path.relative_to(_REPO)} shows Python that does not parse: {broken}"
            ) from broken


def test_every_name_the_documentation_imports_from_reprolith_exists() -> None:
    checked = 0
    for path, block in _blocks():
        for node in ast.walk(ast.parse(block)):
            if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith(
                "reprolith"
            ):
                continue
            module = importlib.import_module(node.module or "reprolith")
            for alias in node.names:
                assert hasattr(module, alias.name), (
                    f"{path.relative_to(_REPO)} imports {alias.name!r} from {node.module}, "
                    "which no longer exists"
                )
                checked += 1
    assert checked >= 20, f"only {checked} imported names found; this would pass vacuously"
