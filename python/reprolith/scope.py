"""The inescapable scope statement.

Every certificate carries this, and it can never be emptied. It is the one sentence
that keeps a reproducibility result from being misread as a correctness or clinical
claim (spec: ``reproduction-certificate`` — "Explicit, unavoidable scope statement").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCOPE_MACHINE = "reproducible-not-correct-not-clinical"

SCOPE_HUMAN = (
    "This certificate attests only to the computational reproducibility of the paper's "
    "own results. It makes no claim about biological correctness, model appropriateness, "
    "or fitness for any clinical or therapeutic decision."
)


@dataclass(frozen=True)
class Scope:
    """A non-empty, two-form scope statement attached to every certificate."""

    machine: str = SCOPE_MACHINE
    human: str = SCOPE_HUMAN

    def __post_init__(self) -> None:
        if not self.machine.strip() or not self.human.strip():
            raise ValueError("scope statement cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {"machine": self.machine, "human": self.human}
