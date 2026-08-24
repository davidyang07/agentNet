from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.engine.state import SecurityState


class ExperimentConfig(BaseModel):
    seed: int
    node_count: int = Field(60, ge=25, le=100)
    edge_density: int = Field(2, ge=1, le=5)
    software_type_count: int = Field(3, ge=1, le=5)
    p_same: float = Field(0.15, ge=0.0, le=1.0)
    p_cross: float = Field(0.03, ge=0.0, le=1.0)
    max_ticks: int = Field(200, ge=1, le=2000)
    detector_sensitivity: float = Field(0.2, ge=0.0, le=1.0)
    defense_enabled: bool = Field(True)
    initial_compromised: Literal["highest_degree", "random_node"] = "highest_degree"


class NodeView(BaseModel):
    id: str
    software_type: str
    security_state: SecurityState
    compromised_by: str | None = None
    tick_compromised: int | None = None


class EdgeView(BaseModel):
    source: str
    target: str


class ExperimentSummary(BaseModel):
    experiment_id: UUID
    status: Literal["running", "paused", "finished", "stopped"]
    sim_tick: int
    config: ExperimentConfig


class SpeedRequest(BaseModel):
    multiplier: float = Field(..., ge=0.25, le=8.0)
