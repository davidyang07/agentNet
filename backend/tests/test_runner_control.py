import asyncio

from app.orchestrator.runner import ExperimentRunner
from app.schemas.events import EventType
from app.schemas.experiment import ExperimentConfig


def _make_runner(**overrides) -> ExperimentRunner:
    config = ExperimentConfig(seed=42, node_count=25, max_ticks=10, **overrides)
    runner = ExperimentRunner(config)
    runner.tick_interval = 0
    return runner


async def _drive_to_finished(runner: ExperimentRunner) -> None:
    await runner.publish_initial()
    await runner._run_loop()


def test_pause_freezes_tick_progression():
    async def run() -> None:
        runner = _make_runner()
        await runner.publish_initial()
        task = asyncio.create_task(runner._run_loop())

        await asyncio.sleep(0)
        runner.pause()
        frozen_tick = runner.state.tick
        for _ in range(5):
            await asyncio.sleep(0)
            assert runner.state.tick == frozen_tick

        runner.resume()
        await task

    asyncio.run(run())


def test_resume_continues_from_exact_suspended_state():
    async def run() -> None:
        runner = _make_runner()
        await runner.publish_initial()
        task = asyncio.create_task(runner._run_loop())

        await asyncio.sleep(0)
        runner.pause()
        frozen_tick = runner.state.tick

        runner.resume()
        await asyncio.sleep(0)
        assert runner.state.tick >= frozen_tick
        await task

    asyncio.run(run())


def test_stop_while_running_clears_task_and_settles():
    async def run() -> None:
        runner = _make_runner()
        await runner.publish_initial()
        runner.start()
        task = runner._task
        await asyncio.sleep(0)

        await runner.stop()

        assert runner._task is None
        assert task is not None
        assert task.cancelled() or task.done()

    asyncio.run(run())


def test_stop_while_paused_clears_task_and_settles():
    async def run() -> None:
        runner = _make_runner()
        await runner.publish_initial()
        runner.start()
        task = runner._task
        await asyncio.sleep(0)
        runner.pause()

        await runner.stop()

        assert runner._task is None
        assert task is not None
        assert task.cancelled() or task.done()

    asyncio.run(run())


def test_stop_called_twice_emits_exactly_one_stopped_event():
    async def run() -> None:
        runner = _make_runner()
        await runner.publish_initial()
        runner.start()
        await asyncio.sleep(0)

        await runner.stop()
        await runner.stop()

        events = runner.bus.since(-1)
        stopped = [e for e in events if e.event_type == EventType.EXPERIMENT_STOPPED]
        assert len(stopped) == 1

    asyncio.run(run())


def test_stop_on_naturally_finished_runner_is_noop():
    async def run() -> None:
        runner = _make_runner()
        await _drive_to_finished(runner)
        assert runner.status == "finished"
        assert runner._task is None

        await runner.stop()

        assert runner.status == "finished"
        assert runner._task is None

    asyncio.run(run())


def test_concurrent_stop_calls_emit_exactly_one_stopped_event():
    async def run() -> None:
        runner = _make_runner()
        await runner.publish_initial()
        runner.start()
        await asyncio.sleep(0)

        results = await asyncio.gather(
            runner.stop(), runner.stop(), return_exceptions=True
        )
        for r in results:
            assert not isinstance(r, Exception)

        events = runner.bus.since(-1)
        stopped = [e for e in events if e.event_type == EventType.EXPERIMENT_STOPPED]
        assert len(stopped) == 1
        assert runner._task is None

    asyncio.run(run())
