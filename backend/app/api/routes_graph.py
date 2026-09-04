"""Security-graph and analysis endpoints (docs/PLAN.md §2.5) over a live
experiment's in-memory WorldState/config -- the same registry.get(id)
pattern routes_experiments.py already uses. History/replay equivalents can
be added later the same way routes_history.py replays topology, once
frontend integration needs them (docs/PLAN.md §9)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.graph.analysis import attack_paths, blast_radius, critical_nodes
from app.graph.builder import build_security_graph
from app.graph.security_graph import SecurityGraph
from app.graph.types import NodeType
from app.metrics import compute as metrics
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.graph import (
    AttackPathsResponse,
    BlastRadiusResponse,
    CriticalNodesResponse,
    CriticalNodeView,
    GraphEdgeView,
    GraphNodeView,
    SecurityGraphView,
)
from app.schemas.metrics import MetricsResponse

router = APIRouter(prefix="/api/experiments", tags=["graph"])


def _runner_for(experiment_id: UUID) -> ExperimentRunner:
    runner = registry.get(experiment_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return runner


def _security_graph_for(experiment_id: UUID) -> SecurityGraph:
    runner = _runner_for(experiment_id)
    return build_security_graph(runner.state, runner.config)


@router.get("/{experiment_id}/graph", response_model=SecurityGraphView)
async def get_security_graph(experiment_id: UUID) -> SecurityGraphView:
    graph = _security_graph_for(experiment_id)
    return SecurityGraphView(
        nodes=[
            GraphNodeView(
                id=n.id, node_type=n.node_type, security_state=n.security_state, attrs=n.attrs
            )
            for n in graph.nodes
        ],
        edges=[
            GraphEdgeView(source=e.source, target=e.target, edge_type=e.edge_type, attrs=e.attrs)
            for e in graph.edges()
        ],
    )


@router.get("/{experiment_id}/analysis/attack-paths", response_model=AttackPathsResponse)
async def get_attack_paths(experiment_id: UUID, source: str, target: str) -> AttackPathsResponse:
    graph = _security_graph_for(experiment_id)
    return AttackPathsResponse(paths=attack_paths(graph, source, target))


@router.get("/{experiment_id}/analysis/blast-radius", response_model=BlastRadiusResponse)
async def get_blast_radius(experiment_id: UUID) -> BlastRadiusResponse:
    graph = _security_graph_for(experiment_id)
    compromised = sorted(graph.compromised_ids())
    reachable = sorted(blast_radius(graph))
    total_agents = len(graph.nodes_of_type(NodeType.AGENT))
    fraction = (len(reachable) / total_agents) if total_agents else 0.0
    return BlastRadiusResponse(compromised=compromised, reachable=reachable, fraction=fraction)


@router.get("/{experiment_id}/analysis/critical-nodes", response_model=CriticalNodesResponse)
async def get_critical_nodes(experiment_id: UUID, top_n: int = 5) -> CriticalNodesResponse:
    graph = _security_graph_for(experiment_id)
    ranked = critical_nodes(graph, top_n=top_n)
    return CriticalNodesResponse(
        nodes=[CriticalNodeView(id=node_id, betweenness=score) for node_id, score in ranked]
    )


@router.get("/{experiment_id}/metrics", response_model=MetricsResponse)
async def get_metrics(experiment_id: UUID) -> MetricsResponse:
    runner = _runner_for(experiment_id)
    graph = build_security_graph(runner.state, runner.config)
    # Bounded by EventBus.RING_SIZE, same limitation every other live-runner
    # event consumer already lives with (docs/PLAN.md §6/§9).
    events = runner.bus.since(-1) or []
    return MetricsResponse(
        compromise_fraction=metrics.compromise_fraction(runner.state),
        retained_utility=metrics.retained_utility(runner.state),
        blast_radius_fraction=metrics.blast_radius_fraction(graph),
        privileged_exposure=metrics.privileged_exposure(graph),
        security_plane_integrity=metrics.security_plane_integrity(graph),
        attack_success_rate=metrics.attack_success_rate(events),
        false_quarantine_rate=metrics.false_quarantine_rate(events),
    )
