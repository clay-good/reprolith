"""Each CI job's pip cache key names the extras that job actually installs.

`actions/setup-python` keys its pip cache on the interpreter version and the hash of the files in
`cache-dependency-path`, and on nothing else. Every job here installs from one `pyproject.toml`, so
every job computed the *same* key while installing a different set of extras: the lightest job
saved a `[dev]`-only cache first and the heavy one got a hit it could not use. Measured on run
45338935301 — `engine (3.9)` spent twenty-three minutes compiling `python-copasi`, which publishes
an sdist and no 3.9 wheel, four times what that job's own tests take.

The fix is a per-job file whose *content* makes the key differ. Its content therefore has to stay
equal to the extras the job installs, and a file whose only job is to be hashed is exactly the kind
that drifts silently: nothing fails when it is wrong, the cache just stops being useful again.

Pure stdlib, so this runs on the dependency-free core gate.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _ROOT / ".github" / "workflows"
_KEYS = _ROOT / ".github" / "cache-keys"


def _jobs(text: str) -> list[str]:
    """The workflow split into one chunk per job, which is as much parsing as this needs."""
    return re.split(r"\n  (?=[a-z_]+:\n)", text)


def test_every_marker_names_the_extras_its_job_installs() -> None:
    checked = 0
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        for block in _jobs(workflow.read_text(encoding="utf-8")):
            marker = re.search(r"\.github/cache-keys/([a-z-]+)\.txt", block)
            if marker is None:
                continue
            install = re.search(r'pip install -e "\.\[([^\]]+)\]"', block)
            # A job may install the package with no extras at all, and its marker says so in
            # words: an empty file would hash like any other empty file.
            extras = install.group(1) if install else "no extras"
            assert "pip install -e" in block, f"{marker.group(1)}: a cache key for a job that installs nothing"
            named = (_KEYS / f"{marker.group(1)}.txt").read_text(encoding="utf-8").strip()
            assert named == extras, (
                f"{marker.group(1)}.txt says {named!r} and its job installs "
                f"{extras!r}; the key no longer tracks the work it is for"
            )
            checked += 1
    assert checked >= 5, f"only {checked} job(s) carry a per-job cache key; this check is thinning"


def test_no_two_jobs_share_a_cache_key() -> None:
    """The defect itself, stated as the thing that must not come back.

    Two jobs with the same `cache-dependency-path` have the same key on the same interpreter, and
    the one that finishes first decides what the other one gets.
    """
    paths: dict[str, str] = {}
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        for block in _jobs(workflow.read_text(encoding="utf-8")):
            if "cache: pip" not in block:
                continue
            name = block.split(":", 1)[0].strip()
            listed = re.search(r"cache-dependency-path: \|\n((?:\s+\S+\n)+)", block)
            assert listed is not None, f"{name}: caches pip without naming what keys the cache"
            key = " ".join(sorted(listed.group(1).split()))
            assert key not in paths, (
                f"{name} and {paths[key]} key their pip cache on the same files, so they share a "
                "cache while installing different things"
            )
            paths[key] = name
    assert len(paths) >= 5, paths
