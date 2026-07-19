# Architecture

## The problem

Tool-using LLM pipelines repeat work and blow through token budgets. This models
a pipeline as a DAG of tool calls and optimizes cost, latency, and success
against an unoptimized baseline. Everything is synthetic and deterministic, so
a run is reproducible.

## How the pieces fit

```mermaid
flowchart TD
    A["tools.py<br/>ToolSpec / ToolRegistry / validators<br/>5 mock tools (TOOL_A..E), token counter"]
    B["dag.py<br/>nodes = tool calls, edges = $ref deps<br/>topo sort -> execution waves"]
    C["executor.py<br/>ToolExecutor"]
    C1["MockToolExecutor (baseline)"]
    C2["OptimizingExecutor"]
    D["budget.py"]
    E["cache.py (two tiers)"]
    F["evaluate.py<br/>baseline vs optimized, metrics, report"]
    G["trace.py<br/>structured events -> JSONL + query API"]

    A -->|normalized specs| B
    B -->|waves| C
    C --> C1
    C --> C2
    C2 --> D
    C2 --> E
    C1 -->|ToolResult per node| F
    C2 -->|ToolResult per node| F
    C2 -.-> G
```

## Sample "linear" pipeline

```mermaid
flowchart LR
    n1["n1: TOOL_A(query=alpha)"]
    n2["n2: TOOL_B(text=n1.results)"]
    n3["n3: TOOL_C(items=n1.results)"]
    n4["n4: TOOL_D(items=n3.filtered)"]
    n5["n5: TOOL_E(data=n2.summary)"]

    n1 --> n2
    n1 --> n3
    n3 --> n4
    n2 --> n5
```

Waves: `[[n1], [n2, n3], [n4, n5]]`. Nodes in the same wave have no dependency
on each other, so they could run together.

## What the optimized path does, per node

1. Budget gate. `TokenBudget.request()` returns ok, truncated, or skipped. Once
   the budget is gone, the remaining nodes are skipped instead of crashing.
2. Cache lookup. Exact match first (hash of tool plus inputs), then similarity
   (hashing embedding, cosine over the threshold). A hit reuses the output, so
   there's no regeneration and the tokens and latency are saved.
3. Execute, then truncate string outputs to the granted slice if the grant was
   only partial.
4. Log one event with the optimization fields in its meta.

The cache is shared across the whole eval suite, so a repeated
`TOOL_A(query="alpha")` in a later pipeline hits a result cached earlier. That's
where most of the savings come from.

## Data types

- `ToolSpec`: id, input/output spec, estimated_tokens, latency, success rate
- `ToolResult`: output, tokens_used, latency_ms, status, cache_hit, cache_kind
- `RunResult`: per-node results plus totals
