"""Trace logging for pipeline runs.

Wraps shared.obs so every tool execution emits one canonical event and the
optimization-specific bits (status, tokens, cache_hit, budget left) ride along
in the event meta. The query helpers are what the eval reads back.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from shared.obs import Observer, read_events


class PipelineLogger:
    def __init__(
        self,
        module: str = "orchestrator",
        sink: Optional[str | Path] = None,
        *,
        deterministic: bool = True,
    ) -> None:
        self.obs = Observer(module, sink=sink, deterministic=deterministic)

    def log_tool(
        self,
        *,
        phase: str,
        node_id: str,
        tool_id: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
        tokens_used: int,
        latency_ms: float,
        status: str,
        cache_hit: bool,
        cache_kind: str,
        budget_remaining: int,
    ) -> None:
        self.obs.emit(
            input={"node_id": node_id, "tool_id": tool_id, "inputs": inputs},
            output={"keys": sorted(output)[:8], "status": status},
            latency_ms=latency_ms,
            level="info" if status == "ok" else "warn",
            meta={
                "phase": phase,
                "tool_id": tool_id,
                "node_id": node_id,
                "tokens_used": tokens_used,
                "status": status,
                "cache_hit": cache_hit,
                "cache_kind": cache_kind,
                "budget_remaining": budget_remaining,
            },
        )

    def events(self) -> list[dict[str, Any]]:
        return [e.canonical() | {"meta": e.meta} for e in self.obs.events]

    def filter(self, **meta_eq: Any) -> list[dict[str, Any]]:
        out = []
        for e in self.obs.events:
            if all(e.meta.get(k) == v for k, v in meta_eq.items()):
                out.append(e.canonical() | {"meta": e.meta})
        return out

    def summary(self) -> dict[str, Any]:
        evs = self.obs.events
        return {
            "events": len(evs),
            "unique_event_ids": len({e.event_id for e in evs}),
            "tools_invoked": sorted({e.meta.get("tool_id") for e in evs if e.meta.get("tool_id")}),
            "cache_hits": sum(1 for e in evs if e.meta.get("cache_hit")),
            "statuses": _counts(e.meta.get("status") for e in evs),
            "total_latency_ms": round(sum(e.latency_ms for e in evs), 3),
        }

    def close(self) -> None:
        self.obs.close()


def _counts(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        if v is None:
            continue
        out[v] = out.get(v, 0) + 1
    return out


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    return read_events(path)
