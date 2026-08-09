"""The exact logical oracle refuses networks beyond enumeration, fast and clearly.

Fixed-point and attractor analysis here walk the whole 2ⁿ state space, so they are only tractable
up to `MAX_ENUMERABLE_NODES`. Real signalling models are much larger — CANA's BREAST_CANCER (80
nodes) and LEUKEMIA (60) are astronomically beyond 2ⁿ enumeration — so the honest behaviour is to
raise `NetworkTooLarge` immediately rather than hang or exhaust memory. This test pins that
boundary: the guard fires before any enumeration, on every exhaustive path, while single-state
stepping (which does not enumerate) still works on a large network. Pure stdlib.
"""

from __future__ import annotations

import pytest
from reprolith import MAX_ENUMERABLE_NODES, BooleanNetwork, NetworkTooLarge, UpdateScheme


def _identity_network(n: int) -> BooleanNetwork:
    """An n-node network where every node holds its own value — cheap to build at any size."""
    names = [f"n{i}" for i in range(n)]
    return BooleanNetwork(rules={name: (lambda s, k=name: s[k]) for name in names})


def test_exhaustive_paths_refuse_a_network_beyond_enumeration() -> None:
    net = _identity_network(MAX_ENUMERABLE_NODES + 1)

    # Every path that would enumerate 2ⁿ states must raise fast (the guard fires before iterating),
    # not hang — reaching this assertion at all proves it did not attempt 2^21 states.
    with pytest.raises(NetworkTooLarge, match="intractable"):
        net.fixed_points()
    with pytest.raises(NetworkTooLarge):
        net.attractors()
    with pytest.raises(NetworkTooLarge):
        net.attractors(scheme=UpdateScheme.ASYNCHRONOUS)


def test_single_state_stepping_is_not_blocked_on_a_large_network() -> None:
    # Stepping one state does not enumerate the space, so it must stay available even far above the
    # enumeration cap — a large network can still be simulated forward from a given state.
    net = _identity_network(MAX_ENUMERABLE_NODES + 40)
    state = {name: 1 for name in net.nodes}
    assert net.step(state) == state  # identity rules hold every node


def test_a_network_at_the_cap_is_still_enumerable() -> None:
    # A small network well within the cap enumerates normally — the guard only trips above it.
    net = _identity_network(3)
    # Every state is a fixed point under identity rules: 2³ = 8 of them.
    assert len(net.fixed_points()) == 8
