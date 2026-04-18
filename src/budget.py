"""Per-pipeline token budget.

Spreads a fixed ceiling across the pipeline's nodes and degrades instead of
crashing when it runs low: a node that would overflow gets truncated to what's
left, and once the budget is gone the rest are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Strategy = Literal["equal", "proportional"]


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class TokenBudget:
    max_total: int
    strategy: Strategy = "proportional"
    spent: int = 0
    allocations: dict[str, int] = field(default_factory=dict)

    def allocate(self, node_estimates: dict[str, int]) -> dict[str, int]:
        if not node_estimates:
            self.allocations = {}
            return {}
        if self.strategy == "equal":
            per = self.max_total // len(node_estimates)
            alloc = {nid: per for nid in node_estimates}
        else:
            total_est = sum(node_estimates.values()) or 1
            alloc = {
                nid: max(1, (est * self.max_total) // total_est)
                for nid, est in node_estimates.items()
            }
        self.allocations = alloc
        return alloc

    @property
    def remaining(self) -> int:
        return self.max_total - self.spent

    def can_afford(self, tokens: int) -> bool:
        return self.spent + tokens <= self.max_total

    def request(self, node_id: str, projected_tokens: int) -> tuple[int, str]:
        """Returns (granted, status) where status is ok / truncated / skipped."""
        if self.remaining <= 0:
            return 0, "skipped"
        if projected_tokens <= self.remaining:
            return projected_tokens, "ok"
        return self.remaining, "truncated"

    def consume(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("cannot consume negative tokens")
        if self.spent + tokens > self.max_total:
            tokens = max(0, self.max_total - self.spent)  # clamp at the ceiling
        self.spent += tokens

    def reset(self) -> None:
        self.spent = 0
        self.allocations = {}


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    return text[: max_tokens * 4]
