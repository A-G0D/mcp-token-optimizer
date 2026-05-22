from src.tools import build_default_registry
from src.budget import TokenBudget
from src.cache import TwoTierCache
from src.executor import MockToolExecutor, OptimizingExecutor


def _reg():
    return build_default_registry()


def test_mock_executor_runs_tool():
    reg = _reg()
    ex = MockToolExecutor(reg)
    res = ex.execute("n1", reg.get("TOOL_A"), {"query": "x"})
    assert res.status == "ok"
    assert "results" in res.output
    assert res.tokens_used > 0


def test_optimizing_executor_cache_hit_second_call():
    reg = _reg()
    cache = TwoTierCache()
    ex = OptimizingExecutor(MockToolExecutor(reg), cache=cache)
    spec = reg.get("TOOL_A")
    first = ex.execute("n1", spec, {"query": "x"})
    second = ex.execute("n2", spec, {"query": "x"})
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.latency_ms <= first.latency_ms


def test_budget_skip_when_exhausted():
    reg = _reg()
    budget = TokenBudget(max_total=1)
    ex = OptimizingExecutor(MockToolExecutor(reg), budget=budget)
    spec = reg.get("TOOL_A")
    ex.execute("n1", spec, {"query": "x"})        # eats the tiny budget
    res = ex.execute("n2", spec, {"query": "y"})  # nothing left
    assert res.status == "skipped"
    assert res.tokens_used == 0


def test_budget_never_exceeds_ceiling():
    reg = _reg()
    budget = TokenBudget(max_total=120)
    ex = OptimizingExecutor(MockToolExecutor(reg), budget=budget)
    for i, tid in enumerate(reg.ids()):
        spec = reg.get(tid)
        ex.execute(f"n{i}", spec, {"query": f"q{i}", "text": "t", "items": [1], "data": {}, "predicate": "p", "criteria": "c"})
    assert budget.spent <= budget.max_total
