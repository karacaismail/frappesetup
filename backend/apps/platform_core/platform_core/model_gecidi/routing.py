"""Pure route selection and failure policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from random import Random


@dataclass(frozen=True)
class Candidate:
    api: str
    model: str
    priority: int = 0
    weight: int = 1
    cost: Decimal | None = None
    remaining_budget: Decimal | None = None
    enabled: bool = True
    cooldown_until: float = 0
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Decision:
    candidate: Candidate
    try_next: bool


def candidates(entries, *, now, mode="priority", required=frozenset(), seed=0):
    eligible = [
        entry for entry in entries
        if entry.enabled and entry.cooldown_until <= now
        and required <= entry.capabilities
        and (entry.remaining_budget is None or (
            entry.remaining_budget > 0
            and (entry.cost is not None and entry.cost <= entry.remaining_budget)
        ))
    ]
    if mode == "priority":
        return sorted(eligible, key=lambda entry: entry.priority)
    if mode == "cost":
        return sorted(eligible, key=lambda entry: (
            entry.cost if entry.cost is not None else Decimal("Infinity"), entry.priority,
        ))
    if mode == "weighted":
        random = Random(seed)
        return sorted(
            [entry for entry in eligible if entry.weight > 0],
            key=lambda entry: random.expovariate(entry.weight),
        )
    raise ValueError("Unsupported route selection")


def on_failure(candidate, code, *, now, cooldown_seconds):
    if code == "authentication":
        return Decision(replace(candidate, enabled=False), True)
    if code in {"rate_limit", "upstream", "timeout"}:
        return Decision(replace(candidate, cooldown_until=now + cooldown_seconds), True)
    return Decision(candidate, False)
