"""Tiny stdlib structured logger. Events go to a JSONL sink (or stay in
memory). In deterministic mode a fake clock + counter-based ids make a run
byte-reproducible, which is what the benchmark relies on.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, TextIO


@dataclass
class LogEvent:
    event_id: str
    timestamp: float
    module: str
    input: dict[str, Any]
    output: dict[str, Any]
    latency_ms: float
    level: str = "info"
    meta: dict[str, Any] = field(default_factory=dict)  # not part of canonical()

    def canonical(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "module": self.module,
            "input": self.input,
            "output": self.output,
            "latency_ms": self.latency_ms,
        }


class _DeterministicClock:
    # advances a fixed tick per read, so timestamps repeat across runs
    def __init__(self, start: float = 0.0, tick: float = 0.001) -> None:
        self._t = start
        self._tick = tick

    def __call__(self) -> float:
        self._t += self._tick
        return self._t


class Observer:
    def __init__(
        self,
        module: str,
        sink: Optional[TextIO | str | Path] = None,
        *,
        deterministic: bool = False,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.module = module
        self.deterministic = deterministic
        self._counter = 0
        self.events: list[LogEvent] = []

        if clock is not None:
            self._clock = clock
        elif deterministic:
            self._clock = _DeterministicClock()
        else:
            self._clock = time.time

        self._own_handle: Optional[TextIO] = None
        if isinstance(sink, (str, Path)):
            path = Path(sink)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._own_handle = path.open("a", encoding="utf-8")
            self._sink: Optional[TextIO] = self._own_handle
        else:
            self._sink = sink

    def _next_id(self) -> str:
        self._counter += 1
        if self.deterministic:
            return f"{self.module}-{self._counter:06d}"
        return uuid.uuid4().hex

    def _latency_clock(self) -> float:
        return self._clock()

    def emit(
        self,
        input: dict[str, Any],
        output: dict[str, Any],
        latency_ms: float,
        *,
        level: str = "info",
        meta: Optional[dict[str, Any]] = None,
    ) -> LogEvent:
        ev = LogEvent(
            event_id=self._next_id(),
            timestamp=self._clock(),
            module=self.module,
            input=input,
            output=output,
            latency_ms=latency_ms,
            level=level,
            meta=meta or {},
        )
        self.events.append(ev)
        if self._sink is not None:
            self._sink.write(json.dumps(ev.canonical(), sort_keys=True) + "\n")
            self._sink.flush()
        return ev

    @contextmanager
    def trace(
        self, input: dict[str, Any], *, level: str = "info"
    ) -> Iterator[dict[str, Any]]:
        # times the block and logs one event; fill the yielded output dict
        out: dict[str, Any] = {}
        start = self._latency_clock()
        try:
            yield out
        finally:
            latency_ms = (self._latency_clock() - start) * 1000.0
            self.emit(input, out, latency_ms, level=level)

    def close(self) -> None:
        if self._own_handle is not None:
            self._own_handle.close()
            self._own_handle = None

    def __enter__(self) -> "Observer":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def read_events(path: str | Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
