# P4 — MCP execution + token optimization

A small experiment in optimizing tool-using LLM pipelines for cost, latency and
success rate. A pipeline is compiled into an execution DAG; an optimizing
executor adds token budgeting and a two-tier cache (exact + similarity) on top
of a plain baseline, and an eval script measures the difference.

Pure stdlib, fully deterministic, no API calls. The tools and data are made up
(`TOOL_A..E`) so the whole thing reproduces byte for byte.

## What's where

- `src/tools.py` — tool specs, validation, the token counter, and the five mock tools
- `src/dag.py` — the DAG: nodes are calls, edges are `$ref` dependencies, topo-sorted into waves
- `src/executor.py` — `MockToolExecutor` (baseline) and `OptimizingExecutor` (cache + budget + logging)
- `src/budget.py` — per-pipeline token ceiling, allocation, truncate/skip
- `src/cache.py` — exact-match cache plus a deterministic similarity fallback
- `src/trace.py` — structured JSONL trace + a query API
- `src/evaluate.py` — runs baseline vs optimized and writes the reports
- `src/orchestrator.py` — resolves `$ref` inputs, runs the DAG, CLI entry point

`docs/architecture.md` has the diagram and data flow.

## Running it

```bash
# from this directory; src/ and shared/ need to be importable
export PYTHONPATH="$PWD"          # PowerShell: $env:PYTHONPATH = "$PWD"

python -m src.orchestrator                  # baseline
python -m src.orchestrator --optimize       # cache + budget
python -m src.orchestrator --optimize --log logs/trace.jsonl

python -m src.evaluate                       # writes eval/COMPARISON.md etc.

python -m pytest tests -q
```

Seed, budget and the cache threshold live in `config.json`.

## Metrics

`token_reduction_pct`, `latency_reduction_pct`, `success_rate`, `cache_hit_rate`,
and success rate under a tight budget. Formulas are in `docs/metrics.md`, the
actual numbers in `eval/COMPARISON.md`. Roughly: ~28% fewer tokens, ~36% lower
latency, cache hit rate around 0.46, success rate 1.0, and it degrades gracefully
when the budget is squeezed.

## Outputs

- `logs/trace.jsonl` — one event per tool execution
- `eval/*.json`, `eval/COMPARISON.md`, `eval/SUMMARY.md` — benchmark results

Everything is seed-locked (`shared/determinism.py`); `tests/test_determinism.py`
checks the metrics come out the same across repeated runs.
