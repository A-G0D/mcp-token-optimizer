"""Tool specs, the token counter, and the five synthetic tools.

The tools are deterministic functions of their inputs (no network), which is
what lets the whole benchmark be byte-stable at a fixed seed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable


def count_tokens(obj: Any) -> int:
    # ~4 chars/token. Crude, but it's the same ruler for baseline and optimized
    # so the comparison stays fair.
    text = obj if isinstance(obj, str) else json.dumps(obj, sort_keys=True, default=str)
    if not text:
        return 0
    return (len(text) + 3) // 4


def stable_hash(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class ToolSpec:
    id: str
    display_name: str
    input_spec: dict[str, str]
    output_spec: dict[str, str]
    estimated_tokens: int
    typical_latency_ms: float
    success_rate_baseline: float
    mock_fn: Callable[[dict[str, Any]], dict[str, Any]]

    def normalized(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "input_spec": dict(self.input_spec),
            "output_spec": dict(self.output_spec),
            "estimated_tokens": self.estimated_tokens,
            "typical_latency_ms": self.typical_latency_ms,
            "success_rate_baseline": self.success_rate_baseline,
        }


@dataclass
class ToolResult:
    tool_id: str
    node_id: str
    output: dict[str, Any]
    tokens_used: int
    latency_ms: float
    status: str = "ok"          # ok | truncated | skipped | error
    cache_hit: bool = False
    cache_kind: str = ""        # "" | exact | similar


class SpecValidationError(ValueError):
    pass


_REQUIRED_FIELDS = (
    "id", "display_name", "input_spec", "output_spec",
    "estimated_tokens", "typical_latency_ms", "success_rate_baseline",
)


def validate_spec(spec: dict[str, Any]) -> None:
    for f in _REQUIRED_FIELDS:
        if f not in spec:
            raise SpecValidationError(f"missing required field: {f}")
    if not isinstance(spec["id"], str) or not spec["id"]:
        raise SpecValidationError("id must be a non-empty string")
    if not isinstance(spec["input_spec"], dict) or not isinstance(spec["output_spec"], dict):
        raise SpecValidationError("input_spec/output_spec must be dicts")
    if not isinstance(spec["estimated_tokens"], int) or spec["estimated_tokens"] <= 0:
        raise SpecValidationError("estimated_tokens must be a positive int")
    if not (0.0 <= float(spec["success_rate_baseline"]) <= 1.0):
        raise SpecValidationError("success_rate_baseline must be in [0,1]")
    if float(spec["typical_latency_ms"]) < 0:
        raise SpecValidationError("typical_latency_ms must be >= 0")


def validate_output_shape(spec: ToolSpec, output: dict[str, Any]) -> None:
    missing = set(spec.output_spec) - set(output)
    if missing:
        raise SpecValidationError(f"{spec.id} output missing fields: {sorted(missing)}")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        validate_spec(spec.normalized())
        if spec.id in self._tools:
            raise SpecValidationError(f"duplicate tool id: {spec.id}")
        self._tools[spec.id] = spec

    def get(self, tool_id: str) -> ToolSpec:
        if tool_id not in self._tools:
            raise KeyError(f"unknown tool: {tool_id}")
        return self._tools[tool_id]

    def ids(self) -> list[str]:
        return sorted(self._tools)

    def __len__(self) -> int:
        return len(self._tools)


def _mk_text(seed_text: str, approx_tokens: int) -> str:
    base = f"{seed_text}:{stable_hash(seed_text)}"
    words = max(1, approx_tokens)
    return " ".join([base] * words)[: approx_tokens * 4]


def _tool_a_search(inputs: dict[str, Any]) -> dict[str, Any]:
    q = str(inputs.get("query", ""))
    return {"results": [f"{q}-doc-{i}-{stable_hash(q + str(i))[:6]}" for i in range(5)]}


def _tool_b_summarize(inputs: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(inputs.get("text", ""), sort_keys=True, default=str)
    return {"summary": _mk_text("summary-" + stable_hash(text), 30)}


def _tool_c_filter(inputs: dict[str, Any]) -> dict[str, Any]:
    items = inputs.get("items", [])
    if not isinstance(items, list):
        items = [items]
    pred = str(inputs.get("predicate", "keep"))
    kept = [x for i, x in enumerate(items) if (i + len(pred)) % 2 == 0]
    return {"filtered": kept}


def _tool_d_rank(inputs: dict[str, Any]) -> dict[str, Any]:
    items = inputs.get("items", [])
    if not isinstance(items, list):
        items = [items]
    ranked = sorted(items, key=lambda x: stable_hash(x))
    return {"ranked": ranked}


def _tool_e_format(inputs: dict[str, Any]) -> dict[str, Any]:
    data = inputs.get("data", inputs)
    return {"formatted": _mk_text("fmt-" + stable_hash(data), 20)}


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ToolSpec("TOOL_A", "search", {"query": "str"}, {"results": "list"},
                          200, 50.0, 0.99, _tool_a_search))
    reg.register(ToolSpec("TOOL_B", "summarize", {"text": "str"}, {"summary": "str"},
                          150, 30.0, 0.98, _tool_b_summarize))
    reg.register(ToolSpec("TOOL_C", "filter", {"items": "list", "predicate": "str"},
                          {"filtered": "list"}, 100, 20.0, 0.99, _tool_c_filter))
    reg.register(ToolSpec("TOOL_D", "rank", {"items": "list", "criteria": "str"},
                          {"ranked": "list"}, 120, 25.0, 0.99, _tool_d_rank))
    reg.register(ToolSpec("TOOL_E", "format", {"data": "dict"}, {"formatted": "str"},
                          80, 15.0, 0.995, _tool_e_format))
    return reg
