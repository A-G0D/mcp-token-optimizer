"""Runs a pipeline end to end: resolve $ref inputs, execute the DAG wave by
wave through the chosen executor, and collect the totals the eval needs.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from shared.determinism import set_seed

from .tools import ToolRegistry, ToolResult, build_default_registry
from .dag import DAG, parse_pipeline_spec
from .budget import TokenBudget
from .cache import TwoTierCache
from .trace import PipelineLogger
from .executor import MockToolExecutor, OptimizingExecutor, ToolExecutor


@dataclass
class RunResult:
    pipeline: str
    optimized: bool
    results: dict[str, ToolResult] = field(default_factory=dict)
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    cache_hits: int = 0
    statuses: dict[str, int] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        ok = sum(1 for r in self.results.values() if r.status in ("ok", "truncated"))
        return ok / len(self.results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline,
            "optimized": self.optimized,
            "node_count": self.node_count,
            "total_tokens": self.total_tokens,
            "total_latency_ms": round(self.total_latency_ms, 3),
            "cache_hits": self.cache_hits,
            "success_rate": round(self.success_rate, 4),
            "statuses": self.statuses,
        }


def _resolve_inputs(inputs: dict[str, Any], results: dict[str, ToolResult]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for k, v in inputs.items():
        if isinstance(v, dict) and "$ref" in v:
            node_id, _, field_name = str(v["$ref"]).partition(".")
            up = results.get(node_id)
            resolved[k] = up.output.get(field_name) if up else None
        else:
            resolved[k] = v
    return resolved


def run_dag(
    dag: DAG,
    registry: ToolRegistry,
    executor: ToolExecutor,
    *,
    pipeline_name: str = "pipeline",
    optimized: bool = False,
) -> RunResult:
    rr = RunResult(pipeline=pipeline_name, optimized=optimized)
    for wave in dag.waves():
        for node_id in wave:
            node = dag.nodes[node_id]
            spec = registry.get(node.tool_id)
            concrete = _resolve_inputs(node.inputs, rr.results)
            res = executor.execute(node_id, spec, concrete)
            rr.results[node_id] = res
            rr.total_tokens += res.tokens_used
            rr.total_latency_ms += res.latency_ms
            if res.cache_hit:
                rr.cache_hits += 1
            rr.statuses[res.status] = rr.statuses.get(res.status, 0) + 1
    return rr


class PipelineOrchestrator:
    def __init__(self, config: Optional[dict[str, Any]] = None,
                 registry: Optional[ToolRegistry] = None) -> None:
        self.config = config or {}
        self.registry = registry or build_default_registry()
        self.seed = int(self.config.get("seed", 1337))
        # one cache for the whole suite so a repeated call in a later pipeline
        # can hit a result cached by an earlier one
        cc = self.config.get("cache", {})
        self.shared_cache = TwoTierCache(
            dim=int(cc.get("embedding_dim", 64)),
            similarity_threshold=float(cc.get("similarity_threshold", 0.92)),
        )

    def run(self, pipeline_spec: dict[str, Any], *, optimize: bool,
            logger: Optional[PipelineLogger] = None) -> RunResult:
        set_seed(self.seed)
        dag = parse_pipeline_spec(pipeline_spec)
        name = pipeline_spec.get("name", "pipeline")
        if not optimize:
            execu: ToolExecutor = MockToolExecutor(self.registry)
            return run_dag(dag, self.registry, execu, pipeline_name=name, optimized=False)

        budget = TokenBudget(
            max_total=int(self.config.get("max_tokens_per_pipeline", 4000)),
            strategy=self.config.get("budget_strategy", "proportional"),
        )
        budget.allocate({
            nd["id"]: self.registry.get(nd["tool"]).estimated_tokens
            for nd in pipeline_spec["nodes"]
        })
        execu = OptimizingExecutor(
            MockToolExecutor(self.registry),
            cache=self.shared_cache,
            budget=budget,
            logger=logger,
            lookup_latency_ms=float(self.config.get("lookup_latency_ms", 1.0)),
        )
        return run_dag(dag, self.registry, execu, pipeline_name=name, optimized=True)


def build_sample_pipelines() -> list[dict[str, Any]]:
    linear = {
        "name": "linear",
        "nodes": [
            {"id": "n1", "tool": "TOOL_A", "inputs": {"query": "alpha"}},
            {"id": "n2", "tool": "TOOL_B", "inputs": {"text": {"$ref": "n1.results"}}},
            {"id": "n3", "tool": "TOOL_C", "inputs": {"items": {"$ref": "n1.results"}, "predicate": "keep"}},
            {"id": "n4", "tool": "TOOL_D", "inputs": {"items": {"$ref": "n3.filtered"}, "criteria": "score"}},
            {"id": "n5", "tool": "TOOL_E", "inputs": {"data": {"$ref": "n2.summary"}}},
        ],
    }
    branching = {
        "name": "branching",
        "nodes": [
            {"id": "n1", "tool": "TOOL_A", "inputs": {"query": "alpha"}},  # repeat -> cache hit
            {"id": "n2", "tool": "TOOL_B", "inputs": {"text": {"$ref": "n1.results"}}},
            {"id": "n3", "tool": "TOOL_C", "inputs": {"items": {"$ref": "n1.results"}, "predicate": "keep"}},
            {"id": "n4", "tool": "TOOL_E", "inputs": {"data": {"$ref": "n2.summary"}}},
        ],
    }
    converging = {
        "name": "converging",
        "nodes": [
            {"id": "n1", "tool": "TOOL_A", "inputs": {"query": "beta"}},
            {"id": "n2", "tool": "TOOL_A", "inputs": {"query": "gamma"}},
            {"id": "n3", "tool": "TOOL_D", "inputs": {"items": {"$ref": "n1.results"}, "criteria": "x"}},
            {"id": "n4", "tool": "TOOL_E", "inputs": {"data": {"$ref": "n3.ranked"}}},
        ],
    }
    return [linear, branching, converging]


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run the token-optimization orchestrator.")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.json"))
    ap.add_argument("--optimize", action="store_true", help="run with cache + budget")
    ap.add_argument("--log", default=None, help="JSONL trace output path")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    orch = PipelineOrchestrator(config)
    logger = PipelineLogger("orchestrator", sink=args.log, deterministic=True) if args.log else None
    for spec in build_sample_pipelines():
        rr = orch.run(spec, optimize=args.optimize, logger=logger)
        print(json.dumps(rr.as_dict(), sort_keys=True))
    if logger:
        logger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
