"""Shared fixtures for Postgres-backed integration tests.

No pytest-asyncio dependency: individual test functions keep this repo's
existing `asyncio.run(main())`-per-test convention (see test_runner_control.py
et al.), each creating and closing its own short-lived pool -- this sidesteps
asyncpg's connections/pools being bound to the event loop that created them,
which a shared session-scoped pool would violate once each test's own
`asyncio.run()` tears its loop down.

Tests are isolated by using a fresh `uuid4()` experiment_id per test rather
than truncating tables between tests: the writer under test acquires its own
connections from the pool and commits per batch (no single wrapping
transaction the test controls could roll that back anyway), so per-row
scoping is both simpler and actually correct here.
"""

import asyncio
import os

# Before anything imports the app: its settings are read once and cached, so
# a bare `pytest` would otherwise run every TestClient(app) against the dev
# database (PLAN 14.3 B.9). Pinned, not defaulted -- a POSTGRES_DB left in
# the shell must not redirect the suite either.
TEST_DB = "agentnet_test"
os.environ["POSTGRES_DB"] = TEST_DB

import pytest  # noqa: E402

from app.config import Settings  # noqa: E402
from app.db import check_postgres_reachable, create_pool  # noqa: E402
from app.persistence.migrate import run_migrations  # noqa: E402

TEST_SETTINGS = Settings(postgres_db=TEST_DB)


def _pg_reachable() -> bool:
    return asyncio.run(check_postgres_reachable(TEST_SETTINGS))


PG_REACHABLE = _pg_reachable()

# CI sets this, so an unreachable Postgres fails the run there instead of
# silently skipping every Postgres-backed test. Locally they still skip.
REQUIRE_POSTGRES = os.environ.get("AGENTNET_REQUIRE_POSTGRES") == "1"


def pytest_sessionstart(session: pytest.Session) -> None:
    if REQUIRE_POSTGRES and not PG_REACHABLE:
        pytest.exit(
            f"AGENTNET_REQUIRE_POSTGRES=1 but Postgres ({TEST_DB}) is not reachable",
            returncode=1,
        )


requires_postgres = pytest.mark.skipif(
    not PG_REACHABLE,
    reason="Postgres not reachable at localhost:5432 (agentnet_test) -- run "
    "`docker compose up postgres`",
)


@pytest.fixture(scope="session", autouse=True)
def _migrate_test_db() -> None:
    if not PG_REACHABLE:
        return

    async def _run() -> None:
        pool = await create_pool(TEST_SETTINGS)
        try:
            await run_migrations(pool)
        finally:
            await pool.close()

    asyncio.run(_run())
