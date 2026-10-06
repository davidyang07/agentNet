"""Security-graph and analysis endpoints (docs/PLAN.md §2.5) over a live
experiment's in-memory WorldState/config -- the same registry.get(id)
pattern routes_experiments.py already uses. History/replay equivalents can
be added later the same way routes_history.py replays topology, once
frontend integration needs them (docs/PLAN.md §9)."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.graph.analysis import attack_paths, blast_radius, critical_nodes, provenance
from app.graph.builder import build_security_graph
from app.graph.security_graph import SecurityGraph
from app.metrics import compute as metrics
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.remediation.analyze import recommend
from app.schemas.graph import (
    AttackPathsResponse,
    BlastRadiusResponse,
    CriticalNodesResponse,
    CriticalNodeView,
    GraphEdgeView,
    GraphNodeView,
    ProvenanceResponse,
    SecurityGraphView,
)
from app.schemas.metrics import MetricsResponse
from app.schemas.remediation import RecommendationView, RemediationResponse

router = APIRouter(prefix="/api/experiments", tags=["graph"])


def _runner_for(experiment_id: UUID) -> ExperimentRunner:
    runner = registry.get(experiment_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return runner


def _security_graph_for(experiment_id: UUID) -> SecurityGraph:
    runner = _runner_for(experiment_id)
    return build_security_graph(runner.state, runner.config)


async def _analyze(experiment_id: UUID, analysis):
    """Runs `analysis(graph)` on the run's current security graph in a worker
    thread: graph analysis is pure CPU, and inside an async route it froze
    every live run and WebSocket for its duration. The state is captured on
    the event loop first -- the runner swaps in a new WorldState each tick and
    never mutates one it has handed out."""
    runner = _runner_for(experiment_id)
    state, config = runner.state, runner.config
    return await asyncio.to_thread(lambda: analysis(build_security_graph(state, config)))


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
    paths = await _analyze(experiment_id, lambda graph: attack_paths(graph, source, target))
    return AttackPathsResponse(paths=paths)


@router.get("/{experiment_id}/analysis/blast-radius", response_model=BlastRadiusResponse)
async def get_blast_radius(experiment_id: UUID) -> BlastRadiusResponse:
    return await _analyze(experiment_id, _blast_radius_response)


def _blast_radius_response(graph: SecurityGraph) -> BlastRadiusResponse:
    return BlastRadiusResponse(
        compromised=sorted(graph.compromised_ids()),
        reachable=sorted(blast_radius(graph)),
        fraction=metrics.blast_radius_fraction(graph),
    )


@router.get("/{experiment_id}/analysis/critical-nodes", response_model=CriticalNodesResponse)
async def get_critical_nodes(
    experiment_id: UUID, top_n: int = Query(5, ge=1)
) -> CriticalNodesResponse:
    ranked = await _analyze(experiment_id, lambda graph: critical_nodes(graph, top_n=top_n))
    return CriticalNodesResponse(
        nodes=[CriticalNodeView(id=node_id, betweenness=score) for node_id, score in ranked]
    )


@router.get("/{experiment_id}/analysis/provenance", response_model=ProvenanceResponse)
async def get_provenance(experiment_id: UUID, node_id: str) -> ProvenanceResponse:
    """Backtraces node_id to its ultimate (patient zero) source via the
    compromised_by chain already carried by AgentNode -- reconstructs the
    causal attack trace (docs/PLAN.md §9's "causal replay/observability")
    without any new persistence, reusing app/graph/analysis.py::provenance
    (already implemented and tested in priority 1)."""
    runner = _runner_for(experiment_id)
    if node_id not in runner.state.nodes:
        raise HTTPException(status_code=404, detail="node not found in this experiment")
    compromised_by = {n.id: n.compromised_by for n in runner.state.nodes.values()}
    return ProvenanceResponse(chain=provenance(compromised_by, node_id))


@router.get("/{experiment_id}/metrics", response_model=MetricsResponse)
async def get_metrics(experiment_id: UUID) -> MetricsResponse:
    runner = _runner_for(experiment_id)
    state, config = runner.state, runner.config
    # The runner's whole-run tally, not the EventBus ring: the ring stops
    # holding a long run's start, which silently zeroed these metrics.
    # Snapshotted on the loop, since the runner keeps folding into it.
    tally = runner.event_tally.snapshot()
    reported = await asyncio.to_thread(
        lambda: metrics.all_metrics(state, build_security_graph(state, config), tally)
    )
    return MetricsResponse(**reported)


@router.get("/{experiment_id}/remediation", response_model=RemediationResponse)
async def get_remediation(experiment_id: UUID) -> RemediationResponse:
    runner = _runner_for(experiment_id)
    graph = build_security_graph(runner.state, runner.config)
    fraction = metrics.compromise_fraction(runner.state)
    integrity = metrics.security_plane_integrity(graph)
    recommendations = recommend(runner.config, fraction, integrity)
    return RemediationResponse(
        recommendations=[
            RecommendationView(description=r.description, config_diff=r.config_diff)
            for r in recommendations
        ]
    )
