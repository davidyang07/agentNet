import asyncio
from typing import Literal
from uuid import UUID, uuid4

from app.engine.propagation import is_finished
from app.engine.tick import advance
from app.engine.topology import build_world
from app.events.bus import EventBus
from app.events.emitter import EventEmitter
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import EdgeView, ExperimentConfig, ExperimentSummary, NodeView
from app.schemas.frames import SnapshotFrame

Status = Literal["running", "paused", "finished", "stopped"]


class InvalidTransitionError(Exception):
    """Raised when a control operation is invalid for the runner's current status."""


class ExperimentRunner:
    """The only place wall-clock time exists."""

    tick_interval_default = 0.25

    def __init__(self, config: ExperimentConfig) -> None:
        self.experiment_id: UUID = uuid4()
        self.config = config
        self.bus = EventBus()
        self._emitter = EventEmitter(self.experiment_id)
        self.status: Status = "running"
        self.state, topology_drafts = build_world(config)
        self._running = True
        self._task: asyncio.Task[None] | None = None
        self.tick_interval: float = self.tick_interval_default
        self._speed: float = 1.0
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._initial_drafts: list[EventDraft] = [
            EventDraft(sim_tick=0, event_type=EventType.EXPERIMENT_STARTED),
            *topology_drafts,
        ]

    async def publish_initial(self) -> None:
        """Awaited synchronously by the create-experiment route before it
        returns, so a client that immediately opens the WS is guaranteed to
        find these events already in the bus buffer — no start-up race."""
        events = self._emitter.emit(self._initial_drafts)
        await self.bus.publish(events)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())

    def pause(self) -> None:
        if self.status == "paused":
            return
        if self.status != "running":
            raise InvalidTransitionError(f"cannot pause an experiment with status {self.status!r}")
        self._pause_event.clear()
        self.status = "paused"

    def resume(self) -> None:
        if self.status == "running":
            return
        if self.status != "paused":
            raise InvalidTransitionError(f"cannot resume an experiment with status {self.status!r}")
        self.status = "running"
        self._pause_event.set()

    def set_speed(self, multiplier: float) -> None:
        if self.status in ("finished", "stopped"):
            raise InvalidTransitionError(
                f"cannot change speed of an experiment with status {self.status!r}"
            )
        self._speed = max(0.25, min(8.0, multiplier))

    async def _run_loop(self) -> None:
        while self._running and not is_finished(self.state, self.config):
            await self._pause_event.wait()
            if not self._running:
                break
            self.state, drafts = advance(self.state, self.config)
            events = self._emitter.emit(drafts)
            await self.bus.publish(events)
            await asyncio.sleep(self.tick_interval / self._speed)
        if self._running:
            self.status = "finished"
        self._task = None

    async def stop(self) -> None:
        if self.status == "finished":
            return
        if self.status == "stopped":
            task = self._task
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return
        self._running = False
        self.status = "stopped"
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if self._task is task:
                self._task = None
        events = self._emitter.emit(
            [EventDraft(sim_tick=self.state.tick, event_type=EventType.EXPERIMENT_STOPPED)]
        )
        await self.bus.publish(events)

    def summary(self) -> ExperimentSummary:
        return ExperimentSummary(
            experiment_id=self.experiment_id,
            status=self.status,
            sim_tick=self.state.tick,
            config=self.config,
        )

    def snapshot(self) -> SnapshotFrame:
        return SnapshotFrame(
            experiment_id=self.experiment_id,
            last_seq=self._emitter.last_seq,
            sim_tick=self.state.tick,
            status=self.status,
            nodes=[
                NodeView(id=n.id, software_type=n.software_type, security_state=n.security_state)
                for n in self.state.nodes.values()
            ],
            edges=[EdgeView(source=a, target=b) for a, b in self.state.edges],
        )
