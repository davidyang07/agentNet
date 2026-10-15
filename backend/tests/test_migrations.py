import asyncio
import uuid

import asyncpg
import pytest

from app.db import create_pool
from app.persistence.migrate import run_migrations

from .conftest import TEST_SETTINGS, requires_postgres

pytestmark = requires_postgres


def test_run_migrations_twice_is_idempotent_and_creates_expected_tables():
    async def run() -> None:
        pool = await create_pool(TEST_SETTINGS)
        try:
            await run_migrations(pool)
            await run_migrations(pool)  # second run must be a no-op, not an error

            tables = {
                row["tablename"]
                for row in await pool.fetch(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            }
            assert {"experiments", "experiment_events", "schema_migrations"} <= tables

            rows = await pool.fetch("SELECT version FROM schema_migrations")
            versions = [row["version"] for row in rows]
            assert versions == sorted(set(versions)), "no duplicate migration rows after re-run"
        finally:
            await pool.close()

    asyncio.run(run())


def test_origin_column_defaults_existing_rows_to_assessment_and_rejects_unknown_values():
    async def run() -> None:
        pool = await create_pool(TEST_SETTINGS)
        experiment_id = uuid.uuid4()
        try:
            await run_migrations(pool)
            # A row written the pre-0002 way, with no origin, is an assessment.
            await pool.execute(
                "INSERT INTO experiments (experiment_id, seed, config, schema_version, app_version)"
                " VALUES ($1, 1, '{}'::jsonb, 1, 'test')",
                experiment_id,
            )
            origin = await pool.fetchval(
                "SELECT origin FROM experiments WHERE experiment_id = $1", experiment_id
            )
            assert origin == "assessment"

            with pytest.raises(asyncpg.CheckViolationError):
                await pool.execute(
                    "UPDATE experiments SET origin = 'bogus' WHERE experiment_id = $1",
                    experiment_id,
                )
        finally:
            await pool.execute("DELETE FROM experiments WHERE experiment_id = $1", experiment_id)
            await pool.close()

    asyncio.run(run())
