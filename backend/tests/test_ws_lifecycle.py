"""WebSocket stream lifecycle (PLAN 14.3 B.1), driven against the handler
directly with an in-memory socket so a regression fails on a timeout instead
of hanging the suite:
- a client that disconnects while the stream is idle is noticed (the handler
  used to notice only when a send failed, so quiet streams never exited);
- a finished run's stream closes once everything was delivered, with a code
  the frontend treats as final;
- a client that falls too far behind is told to resync instead of making the
  server buffer without limit."""

import asyncio
import json

from app.api import ws
from app.orchestrator.registry import registry
from app.orchestrator.runner import ExperimentRunner
from app.schemas.events import EventDraft, EventType
from app.schemas.experiment import ExperimentConfig


class FakeWebSocket:
    def __init__(self, *, block_sends: bool = False) -> None:
        self.sent: list[dict] = []
        self.close_code: int | None = None
        self._inbox: asyncio.Queue[dict] = asyncio.Queue()
        self.sends_allowed = asyncio.Event()
        if not block_sends:
            self.sends_allowed.set()

    async def accept(self) -> None:
        pass

    async def send_text(self, text: str) -> None:
        await self.sends_allowed.wait()
        self.sent.append(json.loads(text))

    async def receive(self) -> dict:
        return await self._inbox.get()

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code

    def disconnect(self) -> None:
        self._inbox.put_nowait({"type": "websocket.disconnect", "code": 1000})


def _runner() -> ExperimentRunner:
    runner = ExperimentRunner(ExperimentConfig(seed=42, node_count=25, max_ticks=3))
    runner.tick_interval = 0
    return runner


def test_close_codes_match_the_frontend():
    # Pinned on both sides (frontend/src/lib/stream/closeCodes.test.ts).
    assert (ws.CLOSE_RESYNC, ws.CLOSE_EXPERIMENT_ENDED, ws.CLOSE_UNKNOWN_EXPERIMENT) == (
        4000,
        4001,
        4004,
    )


def test_unknown_experiment_is_closed_with_a_final_code():
    async def main() -> FakeWebSocket:
        socket = FakeWebSocket()
        runner = _runner()  # never registered
        await asyncio.wait_for(ws.experiment_stream(socket, runner.experiment_id), timeout=2)
        return socket

    assert asyncio.run(main()).close_code == ws.CLOSE_UNKNOWN_EXPERIMENT


def test_a_client_leaving_an_idle_stream_ends_the_handler_and_its_subscription():
    async def main() -> tuple[ExperimentRunner, int]:
        runner = _runner()
        await runner.publish_initial()  # a run that is paused / quiet: nothing more arrives
        registry.add(runner)
        socket = FakeWebSocket()
        try:
            handler = asyncio.create_task(ws.experiment_stream(socket, runner.experiment_id))
            await asyncio.sleep(0.05)
            subscribed = runner.bus.subscriber_count
            socket.disconnect()
            await asyncio.wait_for(handler, timeout=2)
            return runner, subscribed
        finally:
            registry.remove(runner.experiment_id)

    runner, subscribed_while_open = asyncio.run(main())
    assert subscribed_while_open == 1
    assert runner.bus.subscriber_count == 0


def test_a_finished_run_is_delivered_in_full_then_closed_as_ended():
    async def main() -> tuple[ExperimentRunner, FakeWebSocket]:
        runner = _runner()
        await runner.publish_initial()
        await runner._run_loop()
        registry.add(runner)
        socket = FakeWebSocket()
        try:
            await asyncio.wait_for(
                ws.experiment_stream(socket, runner.experiment_id, since_seq=-1), timeout=2
            )
            return runner, socket
        finally:
            registry.remove(runner.experiment_id)

    runner, socket = asyncio.run(main())
    assert socket.close_code == ws.CLOSE_EXPERIMENT_ENDED
    assert [frame["event"]["seq"] for frame in socket.sent] == list(range(runner.last_seq + 1))


def test_a_client_that_falls_behind_is_told_to_resync(monkeypatch):
    monkeypatch.setattr(ws, "STREAM_QUEUE_LIMIT", 3)

    async def main() -> FakeWebSocket:
        runner = _runner()
        await runner.publish_initial()
        registry.add(runner)
        socket = FakeWebSocket(block_sends=True)  # a client too slow to keep up
        try:
            handler = asyncio.create_task(ws.experiment_stream(socket, runner.experiment_id))
            await asyncio.sleep(0.05)
            await runner.bus.publish(
                runner._emitter.emit(
                    [EventDraft(sim_tick=1, event_type=EventType.AGENT_STARTED)] * 10
                )
            )
            socket.sends_allowed.set()
            await asyncio.wait_for(handler, timeout=2)
            return socket
        finally:
            registry.remove(runner.experiment_id)

    socket = asyncio.run(main())
    assert socket.close_code == ws.CLOSE_RESYNC


def test_a_since_seq_beyond_the_run_gets_a_fresh_snapshot():
    # It used to filter out every later event until seq passed since_seq.
    async def main() -> FakeWebSocket:
        runner = _runner()
        await runner.publish_initial()
        await runner._run_loop()
        registry.add(runner)
        socket = FakeWebSocket()
        try:
            await asyncio.wait_for(
                ws.experiment_stream(socket, runner.experiment_id, since_seq=10**9), timeout=2
            )
            return socket
        finally:
            registry.remove(runner.experiment_id)

    socket = asyncio.run(main())
    assert socket.sent[0]["type"] == "snapshot"
