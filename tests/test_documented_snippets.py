"""Every Python snippet in the documentation imports names that exist and parses.

A page that teaches an API rots in one direction: a signature moves, the page keeps saying the old
thing, and a reader who follows it concludes the tool is broken. It is not hypothetical —
`docs/claim-types.md`'s own walkthrough was written calling `logical_solver_pin(nodes=...)`, which is
not that function's signature, and nothing but executing it would have said so.

Executing every snippet is not possible here: several need an optional extra, and one simulates five
hundred subjects. What *is* possible everywhere, in the core job with no extras, is to compile each
block and resolve every name it imports from this package — which is the half of the rot that
actually happens. The blocks that can be run are run where they live
(`tests/test_claim_type_catalogue.py` runs the claim-type page's).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).parent.parent
_PAGES = sorted(_ROOT.glob("docs/*.md")) + [_ROOT / "README.md"]


def _snippets(page: Path) -> list[str]:
    return [part.split("```", 1)[0] for part in page.read_text(encoding="utf-8").split("```python")[1:]]


@pytest.mark.parametrize("page", _PAGES, ids=lambda p: p.name)
def test_every_python_snippet_parses(page: Path) -> None:
    """A snippet that is not Python is a snippet nobody ever ran."""
    for index, snippet in enumerate(_snippets(page)):
        try:
            ast.parse(snippet)
        except SyntaxError as broken:  # pragma: no cover - only when a page is wrong
            raise AssertionError(
                f"{page.name} block {index + 1} is not valid Python: {broken}"
            ) from broken


@pytest.mark.parametrize("page", _PAGES, ids=lambda p: p.name)
def test_every_name_a_snippet_imports_from_reprolith_exists(page: Path) -> None:
    """The rot that actually happens: a name that moved, or was never exported at all."""
    import importlib

    for index, snippet in enumerate(_snippets(page)):
        for node in ast.walk(ast.parse(snippet)):
            if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith("reprolith"):
                continue
            module = importlib.import_module(node.module or "reprolith")
            missing = [alias.name for alias in node.names if not hasattr(module, alias.name)]
            assert not missing, (
                f"{page.name} block {index + 1} imports {missing} from {node.module}, which does "
                "not export them — a reader following this page meets an ImportError"
            )


def test_the_sweep_found_the_pages_that_carry_code() -> None:
    """The check's own population, so a page losing its snippets does not quietly empty it."""
    carrying = {page.name for page in _PAGES if _snippets(page)}
    assert carrying >= {
        "claim-types.md", "fba-oracle.md", "logical-class.md",
        "population-and-estimation.md", "sedml-fast-path.md", "figure-values.md",
    }, f"a documentation page stopped carrying its examples: {sorted(carrying)}"


def test_a_snippet_naming_something_that_does_not_exist_would_fail() -> None:
    """The check is not written so that it can only pass."""
    import importlib

    module = importlib.import_module("reprolith")
    assert not hasattr(module, "logical_solver_pin_with_nodes")
    tree = ast.parse("from reprolith import logical_solver_pin_with_nodes")
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))
    assert [a.name for a in node.names if not hasattr(module, a.name)] == [
        "logical_solver_pin_with_nodes"
    ]
