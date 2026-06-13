# Metrics

`src/evaluate.py` computes these over the three sample pipelines (linear,
branching, converging).

| metric | what it is |
|--------|------------|
| `token_reduction_pct` | `(B_tok - O_tok) / B_tok * 100` |
| `latency_reduction_pct` | `(B_lat - O_lat) / B_lat * 100` |
| `success_rate` | nodes finishing ok/truncated, over total nodes |
| `cache_hit_rate` | cache hits per executed node (optimized run) |
| `optimized_within_ceiling_rate` | pipelines staying under the budget ceiling when squeezed |
| `success_rate_under_constraint` | mean success rate at 1/8 the budget |

`B_*` is the baseline aggregate, `O_*` the optimized one.

## Token model

Tokens are estimated at roughly 4 characters per token (`count_tokens`), applied
the same way to both runs so the comparison is fair. A node's `tokens_used` is
`count_tokens(inputs) + count_tokens(output)`; on a cache hit the output is
reused, so only the input counts.

## Current numbers

See `eval/COMPARISON.md` and `eval/SUMMARY.md`. About 28% token reduction, 36%
latency reduction, cache hit rate around 0.46. Under a 1/8 budget ceiling the
optimized path stays within the ceiling at least as often as the baseline.

Regenerate with `python -m src.evaluate`. They come out the same every run,
which `tests/test_determinism.py` checks.
