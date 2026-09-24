"""JSON result envelope shared by every rg.py command.

Every command prints exactly one JSON object whose ``type`` field discriminates the union:

* a command-specific success type, for example ``{"type": "plan", ...}``; or
* ``{"type": "error", "errors": [{"code", "message", "hint", "context"}, ...]}``.

Errors are collected rather than raised one at a time wherever a command can keep checking, so a
single run reports every problem the caller has to fix.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Problem:
    code: str
    message: str
    hint: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "hint": self.hint, "context": self.context}


class RgError(Exception):
    """One or more problems that stop the current command."""

    def __init__(self, problems: Problem | list[Problem]):
        self.problems = problems if isinstance(problems, list) else [problems]
        super().__init__("; ".join(f"{p.code}: {p.message}" for p in self.problems))

    @classmethod
    def of(cls, code: str, message: str, hint: str = "", **context: Any) -> "RgError":
        return cls(Problem(code, message, hint, context))


class ProblemList:
    """Accumulates problems and raises them together."""

    def __init__(self) -> None:
        self.items: list[Problem] = []

    def add(self, code: str, message: str, hint: str = "", **context: Any) -> None:
        self.items.append(Problem(code, message, hint, context))

    def extend(self, error: RgError) -> None:
        self.items.extend(error.problems)

    def raise_if_any(self) -> None:
        if self.items:
            raise RgError(list(self.items))

    def __bool__(self) -> bool:
        return bool(self.items)


def error_payload(error: RgError) -> dict[str, Any]:
    return {"type": "error", "errors": [p.to_json() for p in error.problems]}


def emit(payload: dict[str, Any], stream=None) -> None:
    if "type" not in payload:
        raise ValueError("Every result payload needs a 'type' discriminator.")
    stream = stream or sys.stdout
    json.dump(payload, stream, indent=2, ensure_ascii=False, default=str)
    stream.write("\n")
