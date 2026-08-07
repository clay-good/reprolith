"""The committed public registry stays consistent with the milestone certificates (spec: certificate-publication).

Dependency-free guard on the artifact `scripts/build_registry.py` produces: if the committed
`datasets/registry.html` drifts from the four classes' milestone certificates, this fails and the
registry must be rebuilt. Reading JSON needs no extras, so it runs in the core CI job.
"""

from __future__ import annotations

import json
from pathlib import Path

from reprolith import certificate_from_content, render_registry

_REPO = Path(__file__).parent.parent
_REGISTRY = _REPO / "datasets" / "registry.html"
_SOURCES = {
    "ode-pkpd": _REPO / "datasets" / "milestone" / "certificates",
    "constraint-based": _REPO / "datasets" / "constraint_based" / "milestone" / "certificates",
    "kinetic": _REPO / "datasets" / "kinetic" / "milestone" / "certificates",
    "logical": _REPO / "datasets" / "logical" / "milestone" / "certificates",
    "stochastic": _REPO / "datasets" / "stochastic" / "milestone" / "certificates",
    "spatial": _REPO / "datasets" / "spatial" / "milestone" / "certificates",
}


def _rebuild() -> str:
    entries = []
    for model_class, directory in _SOURCES.items():
        for path in sorted(directory.glob("*.json")):
            entries.append((model_class, certificate_from_content(json.loads(path.read_text()))))
    return render_registry(entries)


def test_committed_registry_matches_the_milestone_certificates() -> None:
    assert _REGISTRY.read_text(encoding="utf-8") == _rebuild()


def test_registry_lists_every_class_and_certificate() -> None:
    html = _REGISTRY.read_text(encoding="utf-8")
    assert html.count('class="entry"') == 21  # +3 spatial: 1 PK/PD + 4 FBA + 6 kinetic + 4 logical + 3 stochastic + 3 spatial
    for model_class in _SOURCES:
        assert f'data-class="{model_class}"' in html
    # The scope statement travels with the published registry and cannot be emptied.
    assert "clinical" in html.lower()
