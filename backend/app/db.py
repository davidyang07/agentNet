import asyncio

import asyncpg
from fastapi import Depends

from app.config import Settings, get_settings


async def check_postgres_reachable(settings: Settings = Depends(get_settings)) -> bool:
    """Attempt a short-lived Postgres connection. Never raises."""
    try:
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                user=settings.postgres_user,
                password=settings.postgres_password,
                database=settings.postgres_db,
                timeout=2.0,
            ),
            timeout=3.0,
        )
        await conn.close()
        return True
    except (TimeoutError, OSError, asyncpg.PostgresError):
        return False
