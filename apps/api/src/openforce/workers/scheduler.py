from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openforce.config import get_settings
from openforce.db.session import SessionLocal
from openforce.gmail.ingest import ingest_new_emails
from openforce.proposals.service import process_unprocessed_batch


async def _tick() -> None:
    async with SessionLocal() as s:
        await ingest_new_emails(s)
    async with SessionLocal() as s:
        await process_unprocessed_batch(s)


@asynccontextmanager
async def scheduler_lifespan(app):  # noqa: ARG001
    sched = AsyncIOScheduler()
    interval = get_settings().poll_interval_seconds
    sched.add_job(_tick, "interval", seconds=interval, id="poll", coalesce=True, max_instances=1)
    sched.start()
    try:
        yield
    finally:
        sched.shutdown(wait=False)
