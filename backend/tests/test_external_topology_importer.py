import json
from pathlib import Path

import pytest

from app.engine.topology import build_world_from_agents
from app.graph.builder import build_security_graph
from app.graph.types import EdgeType, NodeType
from app.importers.external_topology import (
    ExternalTopology,
    attach_tool_bindings,
    load_topology_json,
    tag_sentinel_agents,
)
from app.schemas.experiment import ExperimentConfig


@pytest.fixture
def sample_topology_path(tmp_path: Path) -> Path:
    data = {
        "agents": ["research_agent", "web_search_tool", "summarizer_agent", "sentinel_agent"],
        "edges": [
            ["research_agent", "web_search_tool"],
            ["research_agent", "summarizer_agent"],
            ["summarizer_agent", "sentinel_agent"],
        ],
        "tool_bindings": {"research_agent": ["web_search"]},
        "sentinel_agents": ["sentinel_agent"],
    }
    path = tmp_path / "topology.json"
    path.write_text(json.dumps(data))
    return path


def test_load_topology_json(sample_topology_path: Path):
    topology = load_topology_json(sample_topology_path)
    assert isinstance(topology, ExternalTopology)
    assert "research_agent" in topology.agents
    assert topology.tool_bindings["research_agent"] == ["web_search"]


def test_attach_tool_bindings_adds_real_tool_nodes(sample_topology_path: Path):
    topology = load_topology_json(sample_topology_path)
    config = ExperimentConfig(seed=1, node_count=25)
    world, _ = build_world_from_agents(
        topology.agents, {tuple(e) for e in topology.edges}, config
    )
    graph = build_security_graph(world, config)
    attach_tool_bindings(graph, topology.tool_bindings)

    tool_nodes = graph.nodes_of_type(NodeType.TOOL)
    assert any(n.id == "tool-web_search" for n in tool_nodes)
    access_edges = [
        e for e in graph.edges(frozenset({EdgeType.CAN_ACCESS})) if e.target == "tool-web_search"
    ]
    assert any(e.source == "research_agent" for e in access_edges)


def test_tag_sentinel_agents_sets_attrs(sample_topology_path: Path):
    topology = load_topology_json(sample_topology_path)
    config = ExperimentConfig(seed=1, node_count=25)
    world, _ = build_world_from_agents(
        topology.agents, {tuple(e) for e in topology.edges}, config
    )
    graph = build_security_graph(world, config)
    tag_sentinel_agents(graph, topology.sentinel_agents)

    node = next(n for n in graph.nodes if n.id == "sentinel_agent")
    assert node.attrs.get("imported_role") == "sentinel"
