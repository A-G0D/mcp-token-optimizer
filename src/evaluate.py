"""Run the sample pipelines baseline vs optimized and report the difference.

Computes token/latency reduction, success rate, cache-hit rate, and a tight
-budget scenario, then writes the JSON + markdown under eval/.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Optional

from .orchestrator import PipelineOrchestrator, RunResult, build_sample_pipelines
from .trace import PipelineLogger


def run_suite(optimize: bool, config: dict[str, Any],
              logger: Optional[PipelineLogger] = None) -> list[RunResult]:
    orch = PipelineOrchestrator(config)
    return [orch.run(spec, optimize=optimize, logger=logger)
            for spec in build_sample_pipelines()]


def aggregate(runs: list[RunResult]) -> dict[str, Any]:
    nodes = sum(r.node_count for r in runs)
    return {
        "pipelines": len(runs),
        "nodes": nodes,
        "total_tokens": sum(r.total_tokens for r in runs),
        "total_latency_ms": round(sum(r.total_latency_ms for r in runs), 3),
        "cache_hits": sum(r.cache_hits for r in runs),
        "cache_hit_rate": round(sum(r.cache_hits for r in runs) / nodes, 4) if nodes else 0.0,
        "success_rate": round(statistics.mean(r.success_rate for r in runs), 4) if runs else 0.0,
    }


def _pct_reduction(base: float, opt: float) -> float:
    return round((base - opt) / base * 100.0, 2) if base else 0.0


def compare(config: dict[str, Any]) -> dict[str, Any]:
    base = run_suite(optimize=False, config=config)
    opt = run_suite(optimize=True, config=config)
    a_base, a_opt = aggregate(base), aggregate(opt)

    comparison = {
        "token_reduction_pct": _pct_reduction(a_base["total_tokens"], a_opt["total_tokens"]),
        "latency_reduction_pct": _pct_reduction(a_base["total_latency_ms"], a_opt["total_latency_ms"]),
        "cache_hit_rate": a_opt["cache_hit_rate"],
        "baseline_success_rate": a_base["success_rate"],
        "optimized_success_rate": a_opt["success_rate"],
    }
    constrained = _constrained_eval(config)
    return {
        "baseline": a_base,
        "optimized": a_opt,
        "comparison": comparison,
        "constrained": constrained,
        "per_pipeline": {
            "baseline": [r.as_dict() for r in base],
            "optimized": [r.as_dict() for r in opt],
        },
    }


def _constrained_eval(config: dict[str, Any]) -> dict[str, Any]:
    tight = dict(config)
    tight["max_tokens_per_pipeline"] = max(1, int(config.get("max_tokens_per_pipeline", 4000)) // 8)
    base = run_suite(optimize=False, config=tight)
    opt = run_suite(optimize=True, config=tight)
    ceiling = tight["max_tokens_per_pipeline"]
    base_within = sum(1 for r in base if r.total_tokens <= ceiling) / len(base)
    opt_within = sum(1 for r in opt if r.total_tokens <= ceiling) / len(opt)
    return {
        "ceiling_per_pipeline": ceiling,
        "baseline_within_ceiling_rate": round(base_within, 4),
        "optimized_within_ceiling_rate": round(opt_within, 4),
        "optimized_success_rate_under_constraint": aggregate(opt)["success_rate"],
    }


def _md_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    head = "| " + " | ".join(cols) + " |\n"
    sep = "| " + " | ".join("---" for _ in cols) + " |\n"
    body = "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)
    return head + sep + body


def write_reports(result: dict[str, Any], eval_dir: str | Path) -> None:
    d = Path(eval_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "baseline_results.json").write_text(
        json.dumps(result["per_pipeline"]["baseline"], indent=2), encoding="utf-8")
    (d / "optimized_results.json").write_text(
        json.dumps(result["per_pipeline"]["optimized"], indent=2), encoding="utf-8")

    c = result["comparison"]
    md = ["# Baseline vs optimized", "",
          "Deterministic run, synthetic data.", "",
          "## Aggregate", "",
          _md_table([
              {"metric": "total tokens", "baseline": result["baseline"]["total_tokens"],
               "optimized": result["optimized"]["total_tokens"]},
              {"metric": "total latency (ms)", "baseline": result["baseline"]["total_latency_ms"],
               "optimized": result["optimized"]["total_latency_ms"]},
              {"metric": "cache hit rate", "baseline": 0.0,
               "optimized": result["optimized"]["cache_hit_rate"]},
              {"metric": "success rate", "baseline": result["baseline"]["success_rate"],
               "optimized": result["optimized"]["success_rate"]},
          ], ["metric", "baseline", "optimized"]),
          "",
          "## Headline deltas", "",
          f"- token reduction: {c['token_reduction_pct']}%",
          f"- latency reduction: {c['latency_reduction_pct']}%",
          f"- cache hit rate: {c['cache_hit_rate']}",
          "",
          "## Under a tight budget", "",
          f"- ceiling/pipeline: {result['constrained']['ceiling_per_pipeline']} tokens",
          f"- baseline within ceiling: {result['constrained']['baseline_within_ceiling_rate']}",
          f"- optimized within ceiling: {result['constrained']['optimized_within_ceiling_rate']}",
          f"- optimized success under constraint: {result['constrained']['optimized_success_rate_under_constraint']}",
          "",
          "## Per-pipeline", "",
          _md_table(result["per_pipeline"]["optimized"],
                    ["pipeline", "total_tokens", "total_latency_ms", "cache_hits", "success_rate"]),
          ]
    (d / "COMPARISON.md").write_text("\n".join(md), encoding="utf-8")
    (d / "SUMMARY.md").write_text(
        "# Eval summary\n\n```json\n" + json.dumps(
            {"comparison": c, "constrained": result["constrained"]}, indent=2) + "\n```\n",
        encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Run the evaluation and write reports.")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.json"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "eval"))
    args = ap.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    result = compare(config)
    write_reports(result, args.out)
    print(json.dumps(result["comparison"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
