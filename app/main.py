import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import discussions, jobs, metrics, sources
from app.db.session import init_db, ping_db
from app.services.scheduler import scheduler_loop


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    scheduler_task = asyncio.create_task(scheduler_loop())
    app.state.scheduler_task = scheduler_task
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="GitHub Discussions", lifespan=lifespan)
app.include_router(sources.router)
app.include_router(discussions.router)
app.include_router(metrics.router)
app.include_router(jobs.router)


@app.get("/health")
def health():
    return {"status": "ok", "database": "ok" if ping_db() else "error"}
