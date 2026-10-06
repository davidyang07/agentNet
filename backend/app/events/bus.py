import asyncio
from collections import deque
from collections.abc import Sequence

from app.schemas.events import Event


class EventBus:
    """Fan-out to live subscribers, plus a bounded replay buffer."""

    RING_SIZE = 2000

    def __init__(self) -> None:
        self._buffer: deque[Event] = deque(maxlen=self.RING_SIZE)
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._overflowed: set[asyncio.Queue[Event]] = set()

    async def publish(self, events: Sequence[Event]) -> None:
        for event in events:
            self._buffer.append(event)
            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Never block the run on a slow consumer: drop the event
                    # for this subscriber and flag it, so the consumer can
                    # resync (a stream) or record an incomplete log (persistence).
                    self._overflowed.add(queue)

    def subscribe(self, maxsize: int = 0) -> "asyncio.Queue[Event]":
        """Registers a queue immediately (synchronously), not lazily on first
        iteration, so a caller can subscribe *before* reading a snapshot/backlog
        without risking a publish slipping through the gap unseen. With a
        maxsize, events published while the queue is full are dropped for
        this subscriber and `overflowed()` turns true."""
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[Event]") -> None:
        self._subscribers.discard(queue)
        self._overflowed.discard(queue)

    def overflowed(self, queue: "asyncio.Queue[Event]") -> bool:
        return queue in self._overflowed

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def since(self, seq: int) -> list[Event] | None:
        """Events with event.seq > seq, or None if seq is outside the buffer."""
        if not self._buffer:
            return []
        oldest = self._buffer[0].seq
        if seq < oldest - 1:
            return None
        return [e for e in self._buffer if e.seq > seq]
