import json

from src.trace import PipelineLogger, load_trace


def _emit(logger, status="ok", cache_hit=False, tool="TOOL_A"):
    logger.log_tool(phase="execute", node_id="n1", tool_id=tool,
                    inputs={"query": "x"}, output={"results": [1]},
                    tokens_used=10, latency_ms=5.0, status=status,
                    cache_hit=cache_hit, cache_kind="exact" if cache_hit else "",
                    budget_remaining=100)


def test_event_has_canonical_schema():
    logger = PipelineLogger("orchestrator", deterministic=True)
    _emit(logger)
    ev = logger.events()[0]
    for key in ("event_id", "timestamp", "module", "input", "output", "latency_ms"):
        assert key in ev
    assert ev["meta"]["tool_id"] == "TOOL_A"


def test_filter_and_summary():
    logger = PipelineLogger("orchestrator", deterministic=True)
    _emit(logger, cache_hit=False)
    _emit(logger, cache_hit=True, tool="TOOL_B")
    assert len(logger.filter(cache_hit=True)) == 1
    s = logger.summary()
    assert s["events"] == 2
    assert s["unique_event_ids"] == 2
    assert s["cache_hits"] == 1
    assert set(s["tools_invoked"]) == {"TOOL_A", "TOOL_B"}


def test_jsonl_sink_roundtrip(tmp_path):
    path = tmp_path / "logs" / "trace.jsonl"
    logger = PipelineLogger("orchestrator", sink=path, deterministic=True)
    _emit(logger)
    _emit(logger)
    logger.close()
    rows = load_trace(path)
    assert len(rows) == 2
    for line in path.read_text(encoding="utf-8").splitlines():
        json.loads(line)
