from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.experiment import ExperimentConfig, ExperimentSummary

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentSummary, status_code=201)
async def create_experiment(config: ExperimentConfig) -> ExperimentSummary:
    runner = ExperimentRunner(config)
    await runner.publish_initial()
    registry.add(runner)
    runner.start()
    return runner.summary()


@router.get("/{experiment_id}", response_model=ExperimentSummary)
async def get_experiment(experiment_id: UUID) -> ExperimentSummary:
    runner = registry.get(experiment_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return runner.summary()


@router.post("/{experiment_id}/stop", response_model=ExperimentSummary)
async def stop_experiment(experiment_id: UUID) -> ExperimentSummary:
    runner = registry.get(experiment_id)
    if runner is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    await runner.stop()
    return runner.summary()
