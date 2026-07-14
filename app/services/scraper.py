import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Discussion,
    DiscussionMetric,
    PipelineJob,
    Source,
    SourceDiscussion,
)
from app.repositories.analytics import refresh_source_analytics_cache
from app.repositories.discussions import (
    METRIC_UPDATE_INTERVAL_MINUTES,
    metric_tier,
    upsert_discussion,
)
from app.services.github_client import GitHubGraphQLClient
from app.services.source_parser import (
    SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
    SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
    SOURCE_TYPE_REPOSITORY,
    split_repo_identifier,
)


scraper_logger = logging.getLogger("github_discussions.scraper")
metrics_logger = logging.getLogger("github_discussions.metrics")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ScraperService:
    def __init__(self, client: GitHubGraphQLClient | None = None):
        self.client = client or GitHubGraphQLClient()

    def scrape_source(
        self,
        db: Session,
        source: Source,
        job_type: str = "new_discussions",
    ) -> PipelineJob:
        if source.source_type not in {
            SOURCE_TYPE_REPOSITORY,
            SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
            SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
        }:
            raise ValueError(
                "Scraping only supports repository, organization discussions, "
                "and organization repositories"
            )
        if job_type not in {"scrape_discussions", "new_discussions"}:
            raise ValueError("Discussion scraping job_type is not supported")

        now = utcnow()
        job = PipelineJob(
            job_type=job_type,
            source_id=source.id,
            status="running",
            discussions_found=0,
            discussions_new=0,
            discussions_updated=0,
            items_failed=0,
            started_at=now,
            created_at=now,
        )
        db.add(job)
        db.flush()

        try:
            scraper_logger.info(
                "Bat dau scrape bai moi | source=%s id=%s type=%s max_count=%s",
                source.identifier,
                source.id,
                source.source_type,
                settings.github_page_size,
            )
            lookback_since = now - timedelta(hours=settings.lookback_hours)
            if source.source_type == SOURCE_TYPE_ORGANIZATION_REPOSITORIES:
                repositories = self.client.fetch_discussion_enabled_repositories(
                    source.identifier
                )
                for repository in repositories:
                    owner, repo = split_repo_identifier(repository.name_with_owner)
                    created_since = self._created_since_for_new_discussions(
                        db,
                        source,
                        lookback_since,
                        job_type,
                        repo_full_name=repository.name_with_owner,
                    )
                    try:
                        items = self.client.fetch_recent_discussions(
                            owner,
                            repo,
                            created_since=created_since,
                            include_comments=source.include_comments,
                        )
                    except Exception:
                        job.items_failed += 1
                        continue

                    self._upsert_items(db, source, job, items, now)
            else:
                if source.source_type == SOURCE_TYPE_REPOSITORY:
                    owner, repo = split_repo_identifier(source.identifier)
                    repo_full_name = source.identifier
                else:
                    owner = source.identifier
                    repo = source.identifier
                    repo_full_name = None
                created_since = self._created_since_for_new_discussions(
                    db,
                    source,
                    lookback_since,
                    job_type,
                    repo_full_name=repo_full_name,
                )
                items = self.client.fetch_recent_discussions(
                    owner,
                    repo,
                    created_since=created_since,
                    include_comments=source.include_comments,
                )
                self._upsert_items(db, source, job, items, now)

            source.is_accessible = True
            source.last_scraped = now
            refresh_source_analytics_cache(db, source, now)
            job.status = "done"
            job.finished_at = utcnow()
            db.commit()
            db.refresh(job)
            scraper_logger.info(
                "Hoan tat scrape bai moi | source=%s id=%s found=%s new=%s updated=%s failed=%s",
                source.identifier,
                source.id,
                job.discussions_found,
                job.discussions_new,
                job.discussions_updated,
                job.items_failed,
            )
            return job
        except Exception as exc:
            source.is_accessible = False
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utcnow()
            db.commit()
            db.refresh(job)
            scraper_logger.exception(
                "Loi scrape bai moi | source=%s id=%s type=%s",
                source.identifier,
                source.id,
                source.source_type,
            )
            raise

    def _created_since_for_new_discussions(
        self,
        db: Session,
        source: Source,
        lookback_since: datetime,
        job_type: str,
        repo_full_name: str | None = None,
    ) -> datetime:
        if job_type != "new_discussions":
            return lookback_since

        latest_created_at = self._latest_discussion_created_at(
            db,
            source,
            repo_full_name=repo_full_name,
        )
        if latest_created_at is None:
            return lookback_since

        latest_boundary = latest_created_at + timedelta(microseconds=1)
        return max(lookback_since, latest_boundary)

    def _latest_discussion_created_at(
        self,
        db: Session,
        source: Source,
        repo_full_name: str | None = None,
    ) -> datetime | None:
        stmt = (
            select(Discussion.discussion_created_at)
            .join(
                SourceDiscussion,
                SourceDiscussion.discussion_id == Discussion.id,
            )
            .where(SourceDiscussion.source_id == source.id)
            .order_by(Discussion.discussion_created_at.desc())
            .limit(1)
        )
        if repo_full_name is not None:
            stmt = stmt.where(Discussion.repo_full_name == repo_full_name)
        return db.scalar(stmt)

    def _upsert_items(
        self,
        db: Session,
        source: Source,
        job: PipelineJob,
        items,
        now: datetime,
    ) -> None:
        for item in items:
            _, created = upsert_discussion(
                db,
                source_id=source.id,
                item=item,
                job_id=job.id,
                now=now,
                include_comments=source.include_comments,
            )
            job.discussions_found += 1
            if created:
                job.discussions_new += 1
            else:
                job.discussions_updated += 1

    def update_due_metrics(self, db: Session) -> PipelineJob:
        now = utcnow()
        job = PipelineJob(
            job_type="update_metrics",
            status="running",
            discussions_found=0,
            discussions_new=0,
            discussions_updated=0,
            items_failed=0,
            started_at=now,
            created_at=now,
        )
        db.add(job)
        db.flush()

        due_discussions = db.scalars(
            select(Discussion)
            .join(
                SourceDiscussion,
                SourceDiscussion.discussion_id == Discussion.id,
            )
            .join(Source, Source.id == SourceDiscussion.source_id)
            .where(
                Source.is_active.is_(True),
                Discussion.is_tracked.is_(True),
                Discussion.next_metric_update <= now,
            )
            .distinct()
        ).all()

        try:
            metrics_logger.info(
                "Bat dau cap nhat metrics | discussions_due=%s",
                len(due_discussions),
            )
            affected_source_ids = set()
            for discussion in due_discussions:
                try:
                    with db.begin_nested():
                        metrics = self.client.fetch_discussion_metrics_by_id(
                            discussion.github_discussion_id
                        )
                        self._update_discussion_metrics(
                            db,
                            discussion,
                            metrics,
                            job.id,
                            now,
                        )
                except SQLAlchemyError:
                    raise
                except Exception:
                    job.items_failed += 1
                    metrics_logger.exception(
                        "Loi cap nhat metrics | discussion_id=%s repo=%s number=%s",
                        discussion.id,
                        discussion.repo_full_name,
                        discussion.discussion_number,
                    )
                    continue
                affected_source_ids.update(
                    self._source_ids_for_discussion(db, discussion.id)
                )
                job.discussions_found += 1
                job.discussions_updated += 1

            for source_id in affected_source_ids:
                source = db.get(Source, source_id)
                if source is not None:
                    refresh_source_analytics_cache(db, source, now)

            job.status = "done"
            job.finished_at = utcnow()
            db.commit()
            db.refresh(job)
            metrics_logger.info(
                "Hoan tat cap nhat metrics | updated=%s failed=%s",
                job.discussions_updated,
                job.items_failed,
            )
            return job
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.items_failed += 1
            job.finished_at = utcnow()
            db.commit()
            db.refresh(job)
            metrics_logger.exception("Loi cap nhat metrics")
            raise

    def _update_discussion_metrics(
        self,
        db: Session,
        discussion: Discussion,
        metrics,
        job_id: int,
        now: datetime,
    ) -> None:
        tier = metric_tier(metrics.comments_count, metrics.upvote_count)

        discussion.comments_count = metrics.comments_count
        discussion.upvote_count = metrics.upvote_count
        discussion.last_metric_update = now
        discussion.next_metric_update = now + timedelta(
            minutes=METRIC_UPDATE_INTERVAL_MINUTES[tier]
        )
        discussion.metric_tier = tier

        db.add(
            DiscussionMetric(
                discussion_id=discussion.id,
                comments_count=metrics.comments_count,
                upvote_count=metrics.upvote_count,
                recorded_at=now,
                job_id=job_id,
            )
        )

    def _source_ids_for_discussion(self, db: Session, discussion_id: int) -> set[int]:
        return set(
            db.scalars(
                select(SourceDiscussion.source_id).where(
                    SourceDiscussion.discussion_id == discussion_id
                )
            ).all()
        )
