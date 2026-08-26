"""Read-only historical endpoints over Postgres. Deliberately does not merge
in currently-live (in-registry) experiments -- conflating the in-memory
registry and Postgres as one listing authority would be exactly the
dual-source-of-truth risk this design otherwise avoids (an open product
question, not resolved here -- see docs/PHASE_1_5_PLAN.md §17)."""

import base64
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request

from app.engine.topology import build_world
from app.schemas.events import INCIDENT_EVENT_TYPES, Event
from app.schemas.experiment import EdgeView, ExperimentConfig, NodeView
from app.schemas.frames import SnapshotFrame
from app.schemas.history import (
    EventHistoryResponse,
    ExperimentDetail,
    ExperimentListItem,
    ExperimentListResponse,
)

router = APIRouter(prefix="/api/experiments", tags=["history"])

DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
DEFAULT_EVENT_LIMIT = 500
MAX_EVENT_LIMIT = 2000

_LIST_COLUMNS = (
    "experiment_id, seed, config, created_at, final_status, "
    "final_sim_tick, final_last_seq, is_complete"
)


def _get_pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "pg_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503, detail="history unavailable: Postgres not connected"
        )
    return pool


def _encode_cursor(created_at: datetime, experiment_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{experiment_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_str, experiment_id_str = raw.split("|", 1)
        return datetime.fromisoformat(created_at_str), UUID(experiment_id_str)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc


def _row_to_list_item(row: asyncpg.Record) -> ExperimentListItem:
    return ExperimentListItem(
        experiment_id=row["experiment_id"],
        seed=row["seed"],
        config=json.loads(row["config"]),
        created_at=row["created_at"],
        final_status=row["final_status"],
        final_sim_tick=row["final_sim_tick"],
        final_last_seq=row["final_last_seq"],
        is_complete=row["is_complete"],
    )


def _row_to_event(row: asyncpg.Record) -> Event:
    return Event(
        event_id=row["event_id"],
        seq=row["seq"],
        sim_tick=row["sim_tick"],
        event_type=row["event_type"],
        agent_id=row["agent_id"],
        source_agent_id=row["source_agent_id"],
        target_agent_id=row["target_agent_id"],
        risk_score=row["risk_score"],
        metadata=json.loads(row["metadata"]),
        schema_version=row["schema_version"],
        experiment_id=row["experiment_id"],
        wall_time=row["wall_time"],
    )


async def _require_experiment_exists(pool: asyncpg.Pool, experiment_id: UUID) -> None:
    exists = await pool.fetchval(
        "SELECT 1 FROM experiments WHERE experiment_id = $1", experiment_id
    )
    if not exists:
        raise HTTPException(status_code=404, detail="experiment not found")


@router.get("", response_model=ExperimentListResponse)
async def list_experiments(
    request: Request,
    status: Literal["finished", "stopped", "incomplete"] | None = None,
    defense_enabled: bool | None = None,
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    cursor: str | None = None,
) -> ExperimentListResponse:
    pool = _get_pool(request)
    where_clauses: list[str] = []
    params: list[object] = []

    if status == "incomplete":
        where_clauses.append("final_status IS NULL")
    elif status is not None:
        params.append(status)
        where_clauses.append(f"final_status = ${len(params)}")

    if defense_enabled is not None:
        params.append(defense_enabled)
        where_clauses.append(f"defense_enabled = ${len(params)}")

    if cursor is not None:
        created_at, experiment_id = _decode_cursor(cursor)
        params.append(created_at)
        params.append(experiment_id)
        where_clauses.append(f"(created_at, experiment_id) < (${len(params) - 1}, ${len(params)})")

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    params.append(limit + 1)
    query = (
        f"SELECT {_LIST_COLUMNS} FROM experiments {where_sql} "
        f"ORDER BY created_at DESC, experiment_id DESC LIMIT ${len(params)}"
    )
    rows = await pool.fetch(query, *params)

    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_row_to_list_item(r) for r in rows]
    next_cursor = (
        _encode_cursor(rows[-1]["created_at"], rows[-1]["experiment_id"]) if has_more else None
    )
    return ExperimentListResponse(items=items, next_cursor=next_cursor)


@router.get("/{experiment_id}/detail", response_model=ExperimentDetail)
async def get_experiment_detail(experiment_id: UUID, request: Request) -> ExperimentDetail:
    pool = _get_pool(request)
    row = await pool.fetchrow(
        f"SELECT {_LIST_COLUMNS}, app_version, schema_version, completed_at "
        "FROM experiments WHERE experiment_id = $1",
        experiment_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return ExperimentDetail(
        **_row_to_list_item(row).model_dump(),
        app_version=row["app_version"],
        schema_version=row["schema_version"],
        completed_at=row["completed_at"],
    )


@router.get("/{experiment_id}/events", response_model=EventHistoryResponse)
async def get_experiment_events(
    experiment_id: UUID,
    request: Request,
    since_seq: int = -1,
    limit: int = Query(DEFAULT_EVENT_LIMIT, ge=1, le=MAX_EVENT_LIMIT),
) -> EventHistoryResponse:
    pool = _get_pool(request)
    await _require_experiment_exists(pool, experiment_id)
    rows = await pool.fetch(
        "SELECT * FROM experiment_events WHERE experiment_id = $1 AND seq > $2 "
        "ORDER BY seq LIMIT $3",
        experiment_id,
        since_seq,
        limit,
    )
    events = [_row_to_event(r) for r in rows]
    next_seq = events[-1].seq if len(events) == limit else None
    return EventHistoryResponse(events=events, next_seq=next_seq)


@router.get("/{experiment_id}/incidents", response_model=EventHistoryResponse)
async def get_experiment_incidents(
    experiment_id: UUID,
    request: Request,
    since_seq: int = -1,
    limit: int = Query(DEFAULT_EVENT_LIMIT, ge=1, le=MAX_EVENT_LIMIT),
) -> EventHistoryResponse:
    pool = _get_pool(request)
    await _require_experiment_exists(pool, experiment_id)
    rows = await pool.fetch(
        "SELECT * FROM experiment_events WHERE experiment_id = $1 AND seq > $2 "
        "AND event_type = ANY($3::text[]) ORDER BY seq LIMIT $4",
        experiment_id,
        since_seq,
        [t.value for t in INCIDENT_EVENT_TYPES],
        limit,
    )
    events = [_row_to_event(r) for r in rows]
    next_seq = events[-1].seq if len(events) == limit else None
    return EventHistoryResponse(events=events, next_seq=next_seq)


@router.get("/{experiment_id}/replay-snapshot", response_model=SnapshotFrame)
async def get_replay_snapshot(experiment_id: UUID, request: Request) -> SnapshotFrame:
    pool = _get_pool(request)
    row = await pool.fetchrow(
        "SELECT config, final_status FROM experiments WHERE experiment_id = $1",
        experiment_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")

    config = ExperimentConfig(**json.loads(row["config"]))
    world, _ = build_world(config)

    # Every topology/seed-compromise event is emitted at sim_tick=0
    # (topology.py's drafts; EXPERIMENT_STARTED too) -- this robustly finds
    # the seq boundary already reflected in this regenerated snapshot,
    # regardless of the initial-event count formula, so the next fetched
    # event page (seq > last_seq) never re-delivers a tick-0 event.
    last_seq = await pool.fetchval(
        "SELECT MAX(seq) FROM experiment_events WHERE experiment_id = $1 AND sim_tick = 0",
        experiment_id,
    )
    if last_seq is None:
        raise HTTPException(
            status_code=404, detail="no tick-0 events persisted for this experiment"
        )

    return SnapshotFrame(
        experiment_id=experiment_id,
        last_seq=last_seq,
        sim_tick=0,
        status=row["final_status"] or "stopped",
        nodes=[
            NodeView(
                id=n.id,
                software_type=n.software_type,
                security_state=n.security_state,
                compromised_by=n.compromised_by,
                tick_compromised=n.tick_compromised,
            )
            for n in world.nodes.values()
        ],
        edges=[EdgeView(source=a, target=b) for a, b in world.edges],
    )
