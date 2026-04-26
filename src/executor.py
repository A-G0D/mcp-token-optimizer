"""Tool executors.

MockToolExecutor is the plain baseline: run the tool, count tokens, done.
OptimizingExecutor wraps a base executor with caching, budget enforcement and
trace logging - the path we benchmark against the baseline.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from .tools import ToolRegistry, ToolResult, ToolSpec, count_tokens, validate_output_shape
from .budget import TokenBudget, truncate_to_tokens
from .cache import TwoTierCache
from .trace import PipelineLogger


class ToolExecutor(Protocol):
    def execute(self, node_id: str, spec: ToolSpec, inputs: dict[str, Any]) -> ToolResult:
        ...


class MockToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, node_id: str, spec: ToolSpec, inputs: dict[str, Any]) -> ToolResult:
        output = spec.mock_fn(inputs)
        validate_output_shape(spec, output)
        tokens = count_tokens(inputs) + count_tokens(output)
        return ToolResult(
            tool_id=spec.id,
            node_id=node_id,
            output=output,
            tokens_used=tokens,
            latency_ms=spec.typical_latency_ms,
            status="ok",
        )


class OptimizingExecutor:
    def __init__(
        self,
        base: ToolExecutor,
        *,
        cache: Optional[TwoTierCache] = None,
        budget: Optional[TokenBudget] = None,
        logger: Optional[PipelineLogger] = None,
        lookup_latency_ms: float = 1.0,
    ) -> None:
        self.base = base
        self.cache = cache
        self.budget = budget
        self.logger = logger
        self.lookup_latency_ms = lookup_latency_ms

    def execute(self, node_id: str, spec: ToolSpec, inputs: dict[str, Any]) -> ToolResult:
        phase = "execute"

        if self.budget is not None:
            projected = spec.estimated_tokens + count_tokens(inputs)
            granted, status = self.budget.request(node_id, projected)
            if status == "skipped":
                res = ToolResult(spec.id, node_id, {}, 0, 0.0, status="skipped")
                self._log(phase, spec, node_id, inputs, res)
                return res
        else:
            granted, status = None, "ok"

        if self.cache is not None:
            cached, kind = self.cache.get(spec.id, inputs)
            if cached is not None:
                # output is reused, so only the input counts toward tokens
                tokens = count_tokens(inputs)
                if self.budget is not None:
                    self.budget.consume(tokens)
                res = ToolResult(spec.id, node_id, cached, tokens,
                                 self.lookup_latency_ms, status="ok",
                                 cache_hit=True, cache_kind=kind)
                self._log(phase, spec, node_id, inputs, res)
                return res

        res = self.base.execute(node_id, spec, inputs)
        if self.budget is not None and status == "truncated":
            for k, v in list(res.output.items()):
                if isinstance(v, str):
                    res.output[k] = truncate_to_tokens(v, max(1, granted))
            res.tokens_used = min(res.tokens_used, max(1, granted))
            res.status = "truncated"

        if self.budget is not None:
            self.budget.consume(res.tokens_used)
        if self.cache is not None and res.status in ("ok", "truncated"):
            self.cache.put(spec.id, inputs, res.output)

        self._log(phase, spec, node_id, inputs, res)
        return res

    def _log(self, phase: str, spec: ToolSpec, node_id: str,
             inputs: dict[str, Any], res: ToolResult) -> None:
        if self.logger is None:
            return
        self.logger.log_tool(
            phase=phase, node_id=node_id, tool_id=spec.id, inputs=inputs,
            output=res.output, tokens_used=res.tokens_used, latency_ms=res.latency_ms,
            status=res.status, cache_hit=res.cache_hit, cache_kind=res.cache_kind,
            budget_remaining=self.budget.remaining if self.budget else -1,
        )
