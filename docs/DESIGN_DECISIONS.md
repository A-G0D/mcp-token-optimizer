# Notes on the design choices

## Stdlib + synthetic tools
I wanted the benchmark numbers to be trustworthy, which mostly means
reproducible. No network, no keys, no real data. The tool outputs are pure
functions of their inputs, so the suite is byte-stable at a fixed seed.

## A hashing "embedding" instead of a real model
The cache needs to show similarity reuse, not just exact matches, but a real
embedder would drag in a heavy dependency and some nondeterminism. A hashing
bag-of-words vector, L2-normalized and cosine-compared, is dependency-free and
deterministic, and good enough to stand in for near-duplicate reuse. The
threshold is configurable.

## Two tiers, exact first
Exact match is O(1) and catches identical repeated calls, which is the common
case (the shared `TOOL_A(query="alpha")` across pipelines). The similarity tier
catches near-duplicates an exact key would miss. Trying exact first avoids the
vector scan when it isn't needed.

## Proportional allocation by default
Tools with bigger nominal outputs get a bigger slice of the ceiling, which is
where the tokens actually go. There's an `equal` strategy too. Either way, the
ceiling is the real guarantee. Allocation is just advisory, and `consume()`
clamps total spend so a pipeline can't go over.

## Degrade instead of erroring
A budget-constrained pipeline should still return something useful. A node that
would overflow gets truncated to what's left; once the budget is gone the rest
are skipped and logged. The run finishes, which is what the under-constraint
success rate measures.

## Simulated latency
Actually sleeping would make the tests slow and wall-clock-dependent. Each tool
carries a `typical_latency_ms` and a cache hit substitutes a small lookup cost,
so the latency reduction is meaningful and reproducible without burning real
time.

## Shared cache across the suite
The realistic win is cross-pipeline reuse over a session, so the eval shares one
cache across all the sample pipelines and the savings reflect that.

## Limits
- The 4-chars-per-token estimate is a proxy, fine for relative comparison but not
  for real billing.
- The hashing embedding has no sense of word order or meaning beyond overlap. A
  real system would drop a proper embedder in behind the same interface.
