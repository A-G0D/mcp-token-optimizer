from src.orchestrator import PipelineOrchestrator, build_sample_pipelines
from src.trace import PipelineLogger


CONFIG = {"seed": 1337, "max_tokens_per_pipeline": 4000, "budget_strategy": "proportional",
          "cache": {"embedding_dim": 64, "similarity_threshold": 0.92}, "lookup_latency_ms": 1.0}


def test_end_to_end_baseline_runs_without_crash():
    orch = PipelineOrchestrator(CONFIG)
    for spec in build_sample_pipelines():
        rr = orch.run(spec, optimize=False)
        assert rr.node_count == len(spec["nodes"])
        assert rr.success_rate == 1.0


def test_end_to_end_optimized_produces_cache_hits():
    orch = PipelineOrchestrator(CONFIG)
    total_hits = 0
    for spec in build_sample_pipelines():
        rr = orch.run(spec, optimize=True)
        total_hits += rr.cache_hits
    assert total_hits > 0  # cache is shared across the suite


def test_refs_resolve_across_nodes():
    orch = PipelineOrchestrator(CONFIG)
    spec = build_sample_pipelines()[0]  # linear
    rr = orch.run(spec, optimize=False)
    assert rr.results["n2"].output.get("summary")
    assert rr.results["n5"].output.get("formatted")


def test_logging_integration_emits_events(tmp_path):
    orch = PipelineOrchestrator(CONFIG)
    logger = PipelineLogger("orchestrator", sink=tmp_path / "t.jsonl", deterministic=True)
    orch.run(build_sample_pipelines()[0], optimize=True, logger=logger)
    logger.close()
    s = logger.summary()
    assert s["events"] == 5
    assert s["unique_event_ids"] == 5
