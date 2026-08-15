"""Canonical encoding is stable regardless of key insertion order."""

from __future__ import annotations

import json

import pytest
from reprolith.canonical import canonical_bytes, canonical_json, content_hash


def test_key_order_does_not_change_bytes() -> None:
    a = {"b": 1, "a": 2, "c": [3, 2, 1]}
    b = {"c": [3, 2, 1], "a": 2, "b": 1}
    assert canonical_bytes(a) == canonical_bytes(b)
    assert content_hash(a) == content_hash(b)


def test_list_order_is_preserved() -> None:
    # Sequences are meaningful data; their order must survive canonicalization.
    assert canonical_json([1, 2, 3]) != canonical_json([3, 2, 1])


def test_hash_is_hex_sha256() -> None:
    digest = content_hash({"x": 1})
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)


def test_output_is_always_valid_json_and_non_finite_is_refused() -> None:
    # Python's json would encode NaN/Infinity as bare tokens no standards-compliant reader can
    # parse. The canonical encoding is the basis for a portable, independently-checkable artifact,
    # so it refuses a non-finite value at its source instead of emitting an unparseable one.
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="non-finite"):
            canonical_json({"value": bad})
        with pytest.raises(ValueError, match="non-finite"):
            content_hash({"series": [1.0, bad]})
    # A finite payload still round-trips through a strict parser (no NaN/Infinity constants).
    text = canonical_json({"a": [1.5, 2.0], "b": -3})
    json.loads(text, parse_constant=lambda _: pytest.fail("non-finite token leaked into output"))
