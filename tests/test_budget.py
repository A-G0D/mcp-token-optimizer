import pytest

from src.budget import TokenBudget, truncate_to_tokens


def test_equal_allocation():
    b = TokenBudget(max_total=300, strategy="equal")
    alloc = b.allocate({"a": 10, "b": 20, "c": 30})
    assert alloc == {"a": 100, "b": 100, "c": 100}


def test_proportional_allocation():
    b = TokenBudget(max_total=600, strategy="proportional")
    alloc = b.allocate({"a": 100, "b": 200})
    assert alloc["b"] > alloc["a"]
    assert sum(alloc.values()) <= 600 + 2  # allow rounding slack


def test_request_ok_truncated_skipped():
    b = TokenBudget(max_total=100)
    assert b.request("n1", 40) == (40, "ok")
    b.consume(40)
    assert b.request("n2", 90) == (60, "truncated")  # 60 left, asked for 90
    b.consume(60)
    assert b.request("n3", 10) == (0, "skipped")  # nothing left


def test_consume_never_exceeds_ceiling():
    b = TokenBudget(max_total=50)
    b.consume(80)
    assert b.spent == 50
    assert b.remaining == 0


def test_consume_negative_rejected():
    with pytest.raises(ValueError):
        TokenBudget(max_total=50).consume(-1)


def test_truncate_to_tokens():
    assert truncate_to_tokens("abcdefgh", 1) == "abcd"
    assert truncate_to_tokens("abc", 0) == ""


def test_reset():
    b = TokenBudget(max_total=100)
    b.consume(50)
    b.reset()
    assert b.spent == 0 and b.allocations == {}
