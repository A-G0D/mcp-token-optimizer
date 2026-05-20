from src.cache import TwoTierCache, embed, cosine


def test_embed_deterministic_and_normalized():
    v1 = embed("order entry module", 64)
    v2 = embed("order entry module", 64)
    assert v1 == v2
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_cosine_identical_is_one():
    v = embed("alpha beta gamma", 64)
    assert abs(cosine(v, v) - 1.0) < 1e-9


def test_exact_hit():
    c = TwoTierCache()
    c.put("TOOL_A", {"query": "x"}, {"results": [1, 2]})
    val, kind = c.get("TOOL_A", {"query": "x"})
    assert val == {"results": [1, 2]}
    assert kind == "exact"
    assert c.stats.exact_hits == 1


def test_miss_then_stats():
    c = TwoTierCache()
    val, kind = c.get("TOOL_A", {"query": "novel"})
    assert val is None and kind == ""
    assert c.stats.misses == 1
    assert c.stats.hit_rate == 0.0


def test_similarity_hit_for_near_duplicate():
    c = TwoTierCache(similarity_threshold=0.5)
    c.put("TOOL_B", {"text": "the quick brown fox jumps"}, {"summary": "s"})
    # same bag of words minus one token -> high cosine, different exact key
    val, kind = c.get("TOOL_B", {"text": "the quick brown fox leaps"})
    assert val == {"summary": "s"}
    assert kind == "similar"
    assert c.stats.similar_hits == 1


def test_high_threshold_blocks_weak_similarity():
    c = TwoTierCache(similarity_threshold=0.99)
    c.put("TOOL_B", {"text": "alpha beta"}, {"summary": "s"})
    val, kind = c.get("TOOL_B", {"text": "totally unrelated words here"})
    assert val is None and kind == ""
