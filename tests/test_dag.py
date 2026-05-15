import pytest

from src.dag import DAG, Node, DAGError, ref, linear_chain, parse_pipeline_spec


def test_add_node_and_duplicate_rejected():
    dag = DAG()
    dag.add_call("n1", "TOOL_A", {"query": "x"})
    with pytest.raises(DAGError):
        dag.add_call("n1", "TOOL_B", {})


def test_dependencies_extracted_from_refs():
    n = Node("n2", "TOOL_B", {"text": ref("n1", "results")})
    assert n.dependencies() == {"n1"}


def test_waves_respect_dependencies():
    dag = linear_chain([
        ("n1", "TOOL_A", {"query": "x"}),
        ("n2", "TOOL_B", {"text": ref("n1", "results")}),
        ("n3", "TOOL_E", {"data": ref("n2", "summary")}),
    ])
    assert dag.waves() == [["n1"], ["n2"], ["n3"]]


def test_branching_waves():
    dag = DAG()
    dag.add_call("n1", "TOOL_A", {"query": "x"})
    dag.add_call("n2", "TOOL_B", {"text": ref("n1", "results")})
    dag.add_call("n3", "TOOL_C", {"items": ref("n1", "results"), "predicate": "p"})
    # n2 and n3 only depend on n1, so they share a wave
    assert dag.waves() == [["n1"], ["n2", "n3"]]


def test_cycle_detection():
    dag = DAG()
    dag.add_call("n1", "TOOL_C", {"items": ref("n2", "ranked"), "predicate": "p"})
    dag.add_call("n2", "TOOL_D", {"items": ref("n1", "filtered"), "criteria": "c"})
    assert dag.detect_cycle() is True
    with pytest.raises(DAGError):
        dag.waves()


def test_unknown_ref_rejected():
    dag = DAG()
    dag.add_call("n1", "TOOL_B", {"text": ref("ghost", "x")})
    with pytest.raises(DAGError):
        dag.waves()


def test_json_round_trip_identical():
    dag = linear_chain([
        ("n1", "TOOL_A", {"query": "x"}),
        ("n2", "TOOL_B", {"text": ref("n1", "results")}),
    ])
    j = dag.to_json()
    dag2 = DAG.from_json(j)
    assert dag2.to_json() == j


def test_parse_pipeline_spec():
    spec = {"nodes": [
        {"id": "n1", "tool": "TOOL_A", "inputs": {"query": "x"}},
        {"id": "n2", "tool": "TOOL_E", "inputs": {"data": ref("n1", "results")}},
    ]}
    dag = parse_pipeline_spec(spec)
    assert dag.topo_order() == ["n1", "n2"]
