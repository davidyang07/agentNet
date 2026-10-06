"""OpenTelemetry trace export (docs/PLAN.md priority 9) over a live
experiment's in-memory event buffer -- same registry.get(id) live-runner
pattern every other new endpoint in this codebase uses (routes_graph.py).
A history/replay equivalent can be added the same way later, once a
persisted-event-log path for it is needed."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.events.bus import EventBus
from app.orchestrator.registry import registry
from app.telemetry.otel_export import build_otel_trace

router = APIRouter(prefix="/api/experiments", tags=["telemetry"])


@router.get("/{experiment_id}/otel-trace")
async def get_otel_trace(experiment_id: UUID) -> dict[str, Any]:
    runner = registry.get(experiment_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    events = runner.bus.since(-1)
    if events is None:
        # The ring (EventBus.RING_SIZE) no longer holds this run's start;
        # exporting what's left would present a partial history as the
        # whole trace.
        raise HTTPException(
            status_code=409,
            detail=(
                f"this run has emitted more than {EventBus.RING_SIZE} events; its full "
                "event log is no longer held in memory, so a complete trace cannot be exported"
            ),
        )
    return build_otel_trace(experiment_id, events)
