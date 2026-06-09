from src.evaluate import compare, run_suite


CONFIG = {"seed": 1337, "max_tokens_per_pipeline": 4000, "budget_strategy": "proportional",
          "cache": {"embedding_dim": 64, "similarity_threshold": 0.92}, "lookup_latency_ms": 1.0}


def test_token_counts_repeat_across_runs():
    totals = []
    for _ in range(3):
        runs = run_suite(optimize=True, config=CONFIG)
        totals.append(tuple(r.total_tokens for r in runs))
    assert totals[0] == totals[1] == totals[2]


def test_comparison_metrics_stable():
    assert compare(CONFIG)["comparison"] == compare(CONFIG)["comparison"]


def test_latency_is_reproducible():
    runs1 = run_suite(optimize=False, config=CONFIG)
    runs2 = run_suite(optimize=False, config=CONFIG)
    assert [r.total_latency_ms for r in runs1] == [r.total_latency_ms for r in runs2]
