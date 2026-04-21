"""Two-tier cache: exact match first, then a similarity fallback.

The similarity tier uses a hashing bag-of-words "embedding" (L2-normalized,
cosine compared) so near-duplicate requests can reuse a result without pulling
in a real embedding model. It's a pure function of the request text, so cache
behavior is reproducible.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from .tools import stable_hash


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def embed(text: str, dim: int = 64) -> list[float]:
    vec = [0.0] * dim
    for tok in _TOKEN_RE.findall(text.lower()):
        h = int(stable_hash(tok), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # inputs are already L2-normalized


@dataclass
class CacheStats:
    lookups: int = 0
    exact_hits: int = 0
    similar_hits: int = 0
    misses: int = 0

    @property
    def hits(self) -> int:
        return self.exact_hits + self.similar_hits

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "lookups": self.lookups,
            "exact_hits": self.exact_hits,
            "similar_hits": self.similar_hits,
            "misses": self.misses,
            "hits": self.hits,
            "hit_rate": round(self.hit_rate, 4),
        }


@dataclass
class _Entry:
    key: str
    vector: list[float]
    value: dict[str, Any]


class TwoTierCache:
    def __init__(self, *, dim: int = 64, similarity_threshold: float = 0.92) -> None:
        self.dim = dim
        self.threshold = similarity_threshold
        self._exact: dict[str, dict[str, Any]] = {}
        self._entries: list[_Entry] = []
        self.stats = CacheStats()

    @staticmethod
    def make_key(tool_id: str, inputs: dict[str, Any]) -> str:
        return f"{tool_id}:{stable_hash(inputs)}"

    @staticmethod
    def _request_text(tool_id: str, inputs: dict[str, Any]) -> str:
        return tool_id + " " + json.dumps(inputs, sort_keys=True, default=str)

    def get(self, tool_id: str, inputs: dict[str, Any]) -> tuple[Optional[dict[str, Any]], str]:
        self.stats.lookups += 1
        key = self.make_key(tool_id, inputs)
        if key in self._exact:
            self.stats.exact_hits += 1
            return self._exact[key], "exact"

        # exact missed; fall back to the nearest stored vector
        vec = embed(self._request_text(tool_id, inputs), self.dim)
        best_sim, best = 0.0, None
        for e in self._entries:
            sim = cosine(vec, e.vector)
            if sim > best_sim:
                best_sim, best = sim, e
        if best is not None and best_sim >= self.threshold:
            self.stats.similar_hits += 1
            return best.value, "similar"

        self.stats.misses += 1
        return None, ""

    def put(self, tool_id: str, inputs: dict[str, Any], value: dict[str, Any]) -> None:
        key = self.make_key(tool_id, inputs)
        self._exact[key] = value
        vec = embed(self._request_text(tool_id, inputs), self.dim)
        self._entries.append(_Entry(key, vec, value))

    def clear(self) -> None:
        self._exact.clear()
        self._entries.clear()
        self.stats = CacheStats()
