"""ModelGateway: the single object real-agent code calls into (never a bare
provider) so every cost/safety control lives in exactly one place
(docs/PHASE_2_PLAN.md §3). One instance per experiment -- constructed by
ExperimentRunner -- so its request budget is genuinely per-experiment, not
global or per-tick.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.gateway.schemas import ModelProvider, ModelProviderError, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)

_RETRY_BACKOFF_S = 0.1


@dataclass(frozen=True)
class GatewayResult:
    """`response` is None on failure. `attempts` is how many provider calls
    were made (0 when the budget was already spent), so every attempt can be
    recorded, not just the one that succeeded."""

    response: ModelResponse | None
    attempts: int


class ModelGateway:
    def __init__(
        self,
        provider: ModelProvider,
        *,
        timeout_s: float,
        max_retries: int,
        max_concurrency: int,
        max_requests_per_experiment: int,
    ) -> None:
        self._provider = provider
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._budget = max_requests_per_experiment
        self._used = 0

    @property
    def requests_used(self) -> int:
        """Provider attempts made so far, retries included."""
        return self._used

    async def complete(self, request: ModelRequest) -> ModelResponse | None:
        return (await self.complete_with_attempts(request)).response

    async def complete_with_attempts(self, request: ModelRequest) -> GatewayResult:
        """A None response means: budget exhausted, the deadline passed, the
        retries ran out, or the provider failed in a way a retry can't fix.
        Never raises for a provider/timeout failure -- a model outage
        degrades this attempt to a controlled failure, never the live run.
        `asyncio.CancelledError` (a BaseException) is never caught here and
        always propagates, so ExperimentRunner.stop()'s task cancellation is
        never silently swallowed mid-call.

        `timeout_s` is a deadline for the whole call, retries included, so
        retries can't multiply it. It starts once the semaphore admits the
        call: time spent queued behind other calls isn't this call's to lose.

        The budget is charged per provider attempt, after acquiring the
        semaphore, never before: checking `self._used` before queuing on the
        semaphore lets multiple callers queued past `max_concurrency` each
        observe the same stale count and all pass the check once the
        semaphore admits them, overrunning the budget under concurrent load
        (real_agent_step's asyncio.gather is exactly this shape whenever a
        tick has more real-real attempts than max_concurrency). Checking and
        incrementing back-to-back with no `await` between them is atomic
        under asyncio's cooperative scheduling."""
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._timeout_s
            attempts = 0
            stopped_by = "retries exhausted"
            last_error = ""
            while attempts <= self._max_retries:
                if attempts:
                    await asyncio.sleep(min(_RETRY_BACKOFF_S, deadline - loop.time()))
                if loop.time() >= deadline:
                    stopped_by = "deadline passed"
                    break
                if self._used >= self._budget:
                    stopped_by = "budget exhausted"
                    break
                self._used += 1
                attempts += 1
                try:
                    async with asyncio.timeout_at(deadline) as timeout:
                        response = await self._provider.complete(request)
                    return GatewayResult(response, attempts)
                except TimeoutError:
                    last_error = "TimeoutError"
                    # The provider's own timeout may clear up; the deadline won't.
                    if timeout.expired():
                        stopped_by = "deadline passed"
                        break
                except ModelProviderError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    if not exc.retryable:
                        stopped_by = "not retryable"
                        break
            # A spent budget fails every later call; one warning per call
            # would flood the log for the rest of the run.
            if attempts:
                logger.warning(
                    "model gateway giving up for agent_id=%s after %d attempt(s), %s: %s",
                    request.agent_id,
                    attempts,
                    stopped_by,
                    last_error,
                )
            return GatewayResult(None, attempts)
