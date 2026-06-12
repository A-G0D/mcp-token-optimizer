# Architecture

## The problem

Tool-using LLM pipelines repeat work and blow through token budgets. This models
a pipeline as a DAG of tool calls and optimizes cost/latency/success against an
unoptimized baseline. Everything is synthetic and deterministic, so a run is
reproducible.

## How the pieces fit

```
 tools.py        ToolSpec / ToolRegistry / validators
                 5 mock tools (TOOL_A..E), token counter
                        |
                        v   normalized specs
 dag.py          nodes = tool calls, edges = $ref deps
                 topo sort -> execution waves
                        |
                        v   waves
 executor.py     ToolExecutor
                   MockToolExecutor (baseline)
                   OptimizingExecutor --> budget.py
                                      \-> cache.py (two tiers)
                        |
                        v   ToolResult per node
 evaluate.py     baseline vs optimized, metrics, report
 trace.py        structured events -> JSONL + query API
```

## Sample "linear" pipeline

```
 n1 TOOL_A(query=alpha)
   |-> n2 TOOL_B(text=n1.results)      wave 1
   |-> n3 TOOL_C(items=n1.results)     wave 1
            |-> n4 TOOL_D(items=n3.filtered)   wave 2
 n2 -------> n5 TOOL_E(data=n2.summary)        wave 2

 waves: [[n1], [n2, n3], [n4, n5]]
```

## What the optimized path does, per node

1. Budget gate. `TokenBudget.request()` returns ok / truncated / skipped. Once
   the budget is gone, the remaining nodes are skipped instead of crashing.
2. Cache lookup. Exact match first (hash of tool + inputs), then similarity
   (hashing embedding, cosine over the threshold). A hit reuses the output, so
   no regeneration and the tokens/latency are saved.
3. Execute, then truncate string outputs to the granted slice if the grant was
   only partial.
4. Log one event with the optimization fields in its meta.

The cache is shared across the whole eval suite, so a repeated
`TOOL_A(query="alpha")` in a later pipeline hits a result cached earlier. That's
where most of the savings come from.

## Data types

- `ToolSpec` — id, input/output spec, estimated_tokens, latency, success rate
- `ToolResult` — output, tokens_used, latency_ms, status, cache_hit, cache_kind
- `RunResult` — per-node results plus totals
