import json

from src.evaluate import compare, run_suite, aggregate, write_reports


CONFIG = {
    "seed": 1337, "max_tokens_per_pipeline": 4000, "budget_strategy": "proportional",
    "cache": {"embedding_dim": 64, "similarity_threshold": 0.92}, "lookup_latency_ms": 1.0,
}


def test_optimized_reduces_tokens_and_latency():
    c = compare(CONFIG)["comparison"]
    assert c["token_reduction_pct"] > 0.0
    assert c["latency_reduction_pct"] > 0.0
    assert c["cache_hit_rate"] > 0.0


def test_at_least_three_pipelines_evaluated():
    runs = run_suite(optimize=True, config=CONFIG)
    assert len(runs) >= 3


def test_success_rate_bounds():
    agg = aggregate(run_suite(optimize=True, config=CONFIG))
    assert 0.0 <= agg["success_rate"] <= 1.0


def test_constrained_eval_keeps_optimized_within_ceiling():
    con = compare(CONFIG)["constrained"]
    assert con["optimized_within_ceiling_rate"] >= con["baseline_within_ceiling_rate"]


def test_write_reports(tmp_path):
    result = compare(CONFIG)
    write_reports(result, tmp_path)
    for name in ("baseline_results.json", "optimized_results.json", "COMPARISON.md", "SUMMARY.md"):
        assert (tmp_path / name).exists()
    data = json.loads((tmp_path / "optimized_results.json").read_text())
    assert isinstance(data, list) and len(data) >= 3
