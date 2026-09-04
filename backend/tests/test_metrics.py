from uuid import uuid4

from app.engine.state import AgentNode, SecurityState, WorldState
from app.graph.security_graph import SecurityGraph
from app.graph.types import EdgeType, GraphEdge, GraphNode, NodeType
from app.metrics.compute import (
    attack_success_rate,
    blast_radius_fraction,
    compromise_fraction,
    false_quarantine_rate,
    privileged_exposure,
    retained_utility,
    security_plane_integrity,
)
from app.schemas.events import Event, EventType


def _event(event_type: EventType, **metadata) -> Event:
    return Event(
        sim_tick=0,
        event_type=event_type,
        event_id=uuid4(),
        seq=0,
        experiment_id=uuid4(),
        wall_time="2026-01-01T00:00:00Z",
        metadata=metadata,
    )


def _world(states: dict[str, SecurityState]) -> WorldState:
    nodes = {
        n: AgentNode(id=n, software_type="sw-a", security_state=state, neighbors=())
        for n, state in states.items()
    }
    return WorldState(tick=0, nodes=nodes, edges=())


def test_compromise_fraction_and_retained_utility():
    world = _world(
        {
            "a": SecurityState.COMPROMISED,
            "b": SecurityState.QUARANTINED,
            "c": SecurityState.HEALTHY,
            "d": SecurityState.HEALTHY,
        }
    )
    assert compromise_fraction(world) == 0.25
    assert retained_utility(world) == 0.5


def test_empty_world_metrics_are_zero_not_a_division_error():
    world = _world({})
    assert compromise_fraction(world) == 0.0
    assert retained_utility(world) == 0.0


def _graph_with_credential_and_resource(compromised: bool) -> SecurityGraph:
    graph = SecurityGraph()
    state = SecurityState.COMPROMISED if compromised else SecurityState.HEALTHY
    graph.add_node(GraphNode(id="agent-000", node_type=NodeType.AGENT, security_state=state))
    graph.add_node(GraphNode(id="credential-000", node_type=NodeType.CREDENTIAL))
    graph.add_node(GraphNode(id="resource-000", node_type=NodeType.RESOURCE))
    graph.add_edge(
        GraphEdge(source="agent-000", target="credential-000", edge_type=EdgeType.USES_CREDENTIAL)
    )
    graph.add_edge(
        GraphEdge(source="credential-000", target="resource-000", edge_type=EdgeType.CAN_ACCESS)
    )
    return graph


def test_privileged_exposure_counts_reachable_credentials_and_resources():
    graph = _graph_with_credential_and_resource(compromised=True)
    assert privileged_exposure(graph) == 2


def test_privileged_exposure_zero_when_nothing_compromised():
    graph = _graph_with_credential_and_resource(compromised=False)
    assert privileged_exposure(graph) == 0


def test_blast_radius_fraction_counts_agents_only():
    graph = _graph_with_credential_and_resource(compromised=True)
    # 1 compromised agent reaches itself + credential + resource, but the
    # fraction denominator is agent count only (1), so it should be >= 1.0.
    assert blast_radius_fraction(graph) == 1.0


def test_security_plane_integrity_is_one_with_no_plane_nodes():
    graph = SecurityGraph()
    graph.add_node(GraphNode(id="agent-000", node_type=NodeType.AGENT))
    assert security_plane_integrity(graph) == 1.0


def test_security_plane_integrity_reflects_compromised_sentinels():
    graph = SecurityGraph()
    graph.add_node(
        GraphNode(
            id="sentinel-000", node_type=NodeType.SENTINEL, security_state=SecurityState.HEALTHY
        )
    )
    graph.add_node(
        GraphNode(
            id="sentinel-001", node_type=NodeType.SENTINEL, security_state=SecurityState.COMPROMISED
        )
    )
    assert security_plane_integrity(graph) == 0.5


def test_attack_success_rate():
    events = [
        _event(EventType.COMPROMISE_SUCCEEDED),
        _event(EventType.COMPROMISE_SUCCEEDED),
        _event(EventType.COMPROMISE_FAILED),
        _event(EventType.AGENT_CREATED),
    ]
    assert attack_success_rate(events) == 2 / 3


def test_attack_success_rate_zero_with_no_attempts():
    assert attack_success_rate([_event(EventType.AGENT_CREATED)]) == 0.0


def test_false_quarantine_rate():
    events = [
        _event(EventType.AGENT_QUARANTINED, legitimate=False),
        _event(EventType.AGENT_QUARANTINED),
        _event(EventType.ANOMALY_DETECTED),
    ]
    assert false_quarantine_rate(events) == 0.5


def test_false_quarantine_rate_zero_with_no_quarantines():
    assert false_quarantine_rate([_event(EventType.AGENT_CREATED)]) == 0.0
