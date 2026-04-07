"""Pipeline as a DAG: nodes are tool calls, edges are data dependencies.

Inputs can be literals or references to another node's output:
    {"query": "python"}                    literal
    {"text": {"$ref": "n1.results"}}       resolved from node n1's output

The DAG topo-sorts into waves (groups with no remaining deps) so independent
calls in a wave could run together.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable


class DAGError(ValueError):
    pass


@dataclass
class Node:
    id: str
    tool_id: str
    inputs: dict[str, Any] = field(default_factory=dict)

    def dependencies(self) -> set[str]:
        deps: set[str] = set()
        for v in self.inputs.values():
            if isinstance(v, dict) and "$ref" in v:
                deps.add(str(v["$ref"]).split(".", 1)[0])
        return deps


class DAG:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[tuple[str, str]] = []  # (from, to)

    def add_node(self, node: Node) -> Node:
        if node.id in self.nodes:
            raise DAGError(f"duplicate node id: {node.id}")
        self.nodes[node.id] = node
        return node

    def add_call(self, node_id: str, tool_id: str, inputs: dict[str, Any]) -> Node:
        return self.add_node(Node(node_id, tool_id, inputs))

    def _rebuild_edges(self) -> None:
        self.edges = []
        for n in self.nodes.values():
            for dep in n.dependencies():
                if dep not in self.nodes:
                    raise DAGError(f"node {n.id} references unknown node {dep}")
                self.edges.append((dep, n.id))

    def detect_cycle(self) -> bool:
        self._rebuild_edges()
        indeg = {nid: 0 for nid in self.nodes}
        for _src, dst in self.edges:
            indeg[dst] += 1
        queue = [n for n, d in indeg.items() if d == 0]
        seen = 0
        while queue:
            cur = queue.pop()
            seen += 1
            for src, dst in self.edges:
                if src == cur:
                    indeg[dst] -= 1
                    if indeg[dst] == 0:
                        queue.append(dst)
        return seen != len(self.nodes)

    def waves(self) -> list[list[str]]:
        if self.detect_cycle():
            raise DAGError("pipeline contains a cycle")
        remaining = dict(self.nodes)
        done: set[str] = set()
        waves: list[list[str]] = []
        while remaining:
            # sorted() keeps wave ordering deterministic
            ready = sorted(
                nid for nid, n in remaining.items() if n.dependencies() <= done
            )
            if not ready:
                raise DAGError("unresolvable dependencies (orphan refs)")
            waves.append(ready)
            for nid in ready:
                done.add(nid)
                del remaining[nid]
        return waves

    def topo_order(self) -> list[str]:
        return [nid for wave in self.waves() for nid in wave]

    def to_json(self) -> str:
        self._rebuild_edges()
        return json.dumps(
            {
                "nodes": [
                    {"id": n.id, "tool_id": n.tool_id, "inputs": n.inputs}
                    for n in self.nodes.values()
                ],
                "edges": [{"from": a, "to": b} for a, b in self.edges],
                "waves": [{"wave": i, "nodes": w} for i, w in enumerate(self.waves())],
            },
            sort_keys=True,
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "DAG":
        data = json.loads(text)
        dag = cls()
        for nd in data["nodes"]:
            dag.add_node(Node(nd["id"], nd["tool_id"], nd.get("inputs", {})))
        dag._rebuild_edges()
        return dag


def ref(node_id: str, field_name: str) -> dict[str, str]:
    return {"$ref": f"{node_id}.{field_name}"}


def linear_chain(specs: Iterable[tuple[str, str, dict[str, Any]]]) -> DAG:
    dag = DAG()
    for nid, tid, inp in specs:
        dag.add_call(nid, tid, inp)
    dag._rebuild_edges()
    return dag


def parse_pipeline_spec(spec: dict[str, Any]) -> DAG:
    dag = DAG()
    for nd in spec["nodes"]:
        dag.add_call(nd["id"], nd["tool"], nd.get("inputs", {}))
    dag._rebuild_edges()
    return dag
