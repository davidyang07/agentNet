import time
from collections.abc import Callable
from uuid import UUID

from app.config import get_settings
from app.orchestrator.runner import ExperimentRunner


class ExperimentRegistry:
    """In-memory experiment registry -- a dict (BRIEF §5). A run that has
    ended is evicted once it has been ended for `finished_run_ttl_s`; its
    durable record lives in Postgres, so memory doesn't grow with every run
    ever created (docs/PLAN.md §14.3 B.2)."""

    def __init__(
        self,
        finished_run_ttl_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runners: dict[UUID, ExperimentRunner] = {}
        self.finished_run_ttl_s = (
            get_settings().finished_run_ttl_s if finished_run_ttl_s is None else finished_run_ttl_s
        )
        self._clock = clock

    def add(self, runner: ExperimentRunner) -> None:
        self._evict_expired()
        self._runners[runner.experiment_id] = runner

    def get(self, experiment_id: UUID) -> ExperimentRunner | None:
        self._evict_expired()
        return self._runners.get(experiment_id)

    def remove(self, experiment_id: UUID) -> None:
        self._runners.pop(experiment_id, None)

    def active_count(self) -> int:
        """Runs still running or paused."""
        return sum(1 for runner in self._runners.values() if runner.ended_at is None)

    def _evict_expired(self) -> None:
        now = self._clock()
        expired = [
            experiment_id
            for experiment_id, runner in self._runners.items()
            if runner.ended_at is not None and now - runner.ended_at >= self.finished_run_ttl_s
        ]
        for experiment_id in expired:
            del self._runners[experiment_id]


registry = ExperimentRegistry()
