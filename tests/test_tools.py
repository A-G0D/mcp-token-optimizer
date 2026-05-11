import pytest

from src.tools import (
    ToolSpec, build_default_registry, count_tokens, stable_hash,
    validate_spec, validate_output_shape, SpecValidationError,
)


def test_registry_has_at_least_five_tools():
    reg = build_default_registry()
    assert len(reg) >= 5
    assert set(reg.ids()) >= {"TOOL_A", "TOOL_B", "TOOL_C", "TOOL_D", "TOOL_E"}


def test_count_tokens_monotonic_and_deterministic():
    assert count_tokens("") == 0
    assert count_tokens("abcd") == 1
    a = count_tokens({"x": list(range(10))})
    b = count_tokens({"x": list(range(10))})
    assert a == b and a > 0


def test_stable_hash_order_independent():
    assert stable_hash({"a": 1, "b": 2}) == stable_hash({"b": 2, "a": 1})


def test_valid_specs_pass():
    for tid in build_default_registry().ids():
        validate_spec(build_default_registry().get(tid).normalized())


@pytest.mark.parametrize("bad", [
    {"display_name": "x"},
    {"id": "", "display_name": "x", "input_spec": {}, "output_spec": {},
     "estimated_tokens": 1, "typical_latency_ms": 1, "success_rate_baseline": 1.0},
])
def test_invalid_specs_rejected(bad):
    with pytest.raises(SpecValidationError):
        validate_spec(bad)


def test_negative_tokens_rejected():
    spec = build_default_registry().get("TOOL_A").normalized()
    spec["estimated_tokens"] = -5
    with pytest.raises(SpecValidationError):
        validate_spec(spec)


def test_duplicate_registration_rejected():
    reg = build_default_registry()
    with pytest.raises(SpecValidationError):
        reg.register(reg.get("TOOL_A"))


def test_each_tool_output_matches_shape():
    reg = build_default_registry()
    samples = {
        "TOOL_A": {"query": "x"}, "TOOL_B": {"text": "hello"},
        "TOOL_C": {"items": [1, 2, 3], "predicate": "p"},
        "TOOL_D": {"items": ["b", "a"], "criteria": "c"},
        "TOOL_E": {"data": {"k": "v"}},
    }
    for tid, inp in samples.items():
        spec = reg.get(tid)
        out = spec.mock_fn(inp)
        validate_output_shape(spec, out)


def test_output_shape_mismatch_raises():
    spec = build_default_registry().get("TOOL_A")
    with pytest.raises(SpecValidationError):
        validate_output_shape(spec, {"wrong": 1})


def test_mock_execution_is_deterministic():
    reg = build_default_registry()
    a = reg.get("TOOL_A").mock_fn({"query": "python"})
    b = reg.get("TOOL_A").mock_fn({"query": "python"})
    assert a == b
