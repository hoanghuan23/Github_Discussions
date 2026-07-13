from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import discussions, jobs, metrics, sources
from app.db.session import init_db, ping_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="GitHub Discussions", lifespan=lifespan)
app.include_router(sources.router)
app.include_router(discussions.router)
app.include_router(metrics.router)
app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"status": "ok", "database": "ok" if ping_db() else "error"}
