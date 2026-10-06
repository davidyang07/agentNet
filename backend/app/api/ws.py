import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.orchestrator.registry import registry
from app.schemas.frames import EventFrame

router = APIRouter()

# Close codes, pinned on both sides (frontend/src/lib/stream/closeCodes.ts).
# The client reconnects after CLOSE_RESYNC; the other two are final --
# nothing more will ever arrive, so reconnecting would only spin.
CLOSE_RESYNC = 4000
CLOSE_EXPERIMENT_ENDED = 4001
CLOSE_UNKNOWN_EXPERIMENT = 4004

# Events a stream may fall behind by before the client is told to resync,
# rather than the server buffering a slow client without limit.
STREAM_QUEUE_LIMIT = 10_000


async def _client_gone(websocket: WebSocket) -> None:
    """Returns once the client disconnects. The protocol is server-to-client
    only, so anything the client sends is ignored -- but waiting on receive()
    is the only way to notice a disconnect while there is nothing to send."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


@router.websocket("/api/experiments/{experiment_id}/stream")
async def experiment_stream(
    websocket: WebSocket, experiment_id: UUID, since_seq: int | None = None
) -> None:
    runner = registry.get(experiment_id)
    # Accept before any close: closing during the handshake is answered with
    # HTTP 403, which a browser reports only as an abnormal 1006 with no code
    # -- indistinguishable from a network drop, so it would retry forever.
    await websocket.accept()
    if runner is None:
        await websocket.close(code=CLOSE_UNKNOWN_EXPERIMENT)
        return

    # Subscribe *before* reading any snapshot/backlog so a concurrent publish
    # can never slip through the gap between the two.
    queue = runner.bus.subscribe(maxsize=STREAM_QUEUE_LIMIT)
    client_gone = asyncio.ensure_future(_client_gone(websocket))
    ended = asyncio.ensure_future(runner.ended.wait())
    try:
        backlog = None
        if since_seq is not None and since_seq <= runner.last_seq:
            backlog = runner.bus.since(since_seq)

        if backlog is None:
            snapshot = runner.snapshot()
            await websocket.send_text(snapshot.model_dump_json())
            last_sent_seq = snapshot.last_seq
        else:
            last_sent_seq = since_seq
            for event in backlog:
                await websocket.send_text(EventFrame(event=event).model_dump_json())
                last_sent_seq = event.seq

        while True:
            next_event = asyncio.ensure_future(queue.get())
            done, _ = await asyncio.wait(
                {next_event, client_gone, ended}, return_when=asyncio.FIRST_COMPLETED
            )
            if next_event in done:
                event = next_event.result()
                if event.seq > last_sent_seq:
                    await websocket.send_text(EventFrame(event=event).model_dump_json())
                    last_sent_seq = event.seq
                if runner.bus.overflowed(queue):
                    await websocket.close(code=CLOSE_RESYNC)
                    return
                continue
            next_event.cancel()
            if client_gone in done:
                return
            # The run has ended (its last event was published before `ended`
            # was set) and the queue is drained, so everything is delivered.
            if queue.empty():
                await websocket.close(code=CLOSE_EXPERIMENT_ENDED)
                return
    except WebSocketDisconnect:
        pass
    finally:
        client_gone.cancel()
        ended.cancel()
        runner.bus.unsubscribe(queue)
