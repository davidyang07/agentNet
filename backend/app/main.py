from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_experiments, routes_schema, ws
from app.config import get_settings
from app.db import check_postgres_reachable

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_experiments.router)
app.include_router(routes_schema.router)
app.include_router(ws.router)


@app.get("/health")
async def health(reachable: bool = Depends(check_postgres_reachable)) -> dict[str, str]:
    return {"status": "ok", "postgres": "reachable" if reachable else "unreachable"}
