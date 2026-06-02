# Baseline vs optimized

Deterministic run, synthetic data.

## Aggregate

| metric | baseline | optimized |
| --- | --- | --- |
| total tokens | 662 | 476 |
| total latency (ms) | 395.0 | 251.0 |
| cache hit rate | 0.0 | 0.4615 |
| success rate | 1.0 | 1.0 |


## Headline deltas

- token reduction: 28.1%
- latency reduction: 36.46%
- cache hit rate: 0.4615

## Under a tight budget

- ceiling/pipeline: 500 tokens
- baseline within ceiling: 1.0
- optimized within ceiling: 1.0
- optimized success under constraint: 1.0

## Per-pipeline

| pipeline | total_tokens | total_latency_ms | cache_hits | success_rate |
| --- | --- | --- | --- | --- |
| linear | 208 | 121.0 | 1 | 1.0 |
| branching | 104 | 4.0 | 4 | 1.0 |
| converging | 164 | 126.0 | 1 | 1.0 |
