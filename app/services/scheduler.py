import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Discussion, Source
from app.db.session import SessionLocal
from app.services.scraper import ScraperService, utcnow
from app.services.source_parser import (
    SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
    SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
    SOURCE_TYPE_REPOSITORY,
)


logger = logging.getLogger("github_discussions.scheduler")

SUPPORTED_SOURCE_TYPES = {
    SOURCE_TYPE_REPOSITORY,
    SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
    SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
}


@dataclass(frozen=True)
class SchedulerRunResult:
    sources_due: int
    metrics_due: int
    sources_processed: int
    posts_processed: int
    posts_expired: int
    items_failed: int


def _due_source_ids(db, now):
    return db.scalars(
        select(Source.id)
        .where(
            Source.is_active.is_(True),
            Source.source_type.in_(SUPPORTED_SOURCE_TYPES),
            or_(Source.next_scrape.is_(None), Source.next_scrape <= now),
        )
        .order_by(Source.next_scrape.is_not(None), Source.next_scrape, Source.id)
    ).all()


def _due_metrics_count(db, now) -> int:
    return (
        db.scalar(
            select(func.count(Discussion.id)).where(
                Discussion.is_tracked.is_(True),
                Discussion.next_metric_update <= now,
            )
        )
        or 0
    )


def run_due_once(
    session_factory: sessionmaker = SessionLocal,
    scraper_factory=ScraperService,
) -> SchedulerRunResult:
    now = utcnow()
    with session_factory() as db:
        source_ids = _due_source_ids(db, now)
        metrics_due = _due_metrics_count(db, now)

    sources_due = len(source_ids)
    logger.info(
        "Scheduler bat dau chu ky | sources_due=%s metrics_due=%s",
        sources_due,
        metrics_due,
    )

    sources_processed = 0
    posts_processed = 0
    posts_expired = 0
    items_failed = 0

    if sources_due:
        logger.info("Scheduler bat dau scrape bai moi | sources_due=%s", sources_due)

    for source_id in source_ids:
        with session_factory() as db:
            source = db.get(Source, source_id)
            if source is None or not source.is_active:
                posts_expired += 1
                continue

            source_name = source.identifier
            logger.info(
                "Bat dau scrape bai moi | source=%s id=%s type=%s",
                source_name,
                source.id,
                source.source_type,
            )
            try:
                job = scraper_factory().scrape_source(
                    db,
                    source,
                    job_type="new_discussions",
                )
            except Exception:
                items_failed += 1
                logger.exception(
                    "Loi scrape bai moi | source=%s id=%s type=%s",
                    source_name,
                    source_id,
                    source.source_type,
                )
                continue

            sources_processed += 1
            posts_processed += job.discussions_found
            items_failed += job.items_failed
            logger.info(
                "Hoan tat scrape bai moi | source=%s id=%s found=%s new=%s updated=%s failed=%s",
                source_name,
                source_id,
                job.discussions_found,
                job.discussions_new,
                job.discussions_updated,
                job.items_failed,
            )

    if metrics_due:
        logger.info("Bat dau cap nhat metrics | discussions_due=%s", metrics_due)
        with session_factory() as db:
            try:
                job = scraper_factory().update_due_metrics(db)
            except Exception:
                items_failed += 1
                logger.exception(
                    "Loi cap nhat metrics | discussions_due=%s",
                    metrics_due,
                )
            else:
                posts_processed += job.discussions_found
                items_failed += job.items_failed
                logger.info(
                    "Hoan tat cap nhat metrics | updated=%s failed=%s",
                    job.discussions_updated,
                    job.items_failed,
                )

    logger.info(
        "Scheduler hoan tat chu ky | sources_processed=%s posts_processed=%s posts_expired=%s",
        sources_processed,
        posts_processed,
        posts_expired,
    )

    return SchedulerRunResult(
        sources_due=sources_due,
        metrics_due=metrics_due,
        sources_processed=sources_processed,
        posts_processed=posts_processed,
        posts_expired=posts_expired,
        items_failed=items_failed,
    )


async def scheduler_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_due_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler gap loi ngoai y muon")
        await asyncio.sleep(settings.scheduler_interval_seconds)
