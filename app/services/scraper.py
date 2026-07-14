from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Discussion, PipelineJob, Source
from app.repositories.analytics import refresh_source_analytics_cache
from app.repositories.discussions import upsert_discussion
from app.services.github_client import GitHubGraphQLClient
from app.services.source_parser import (
    SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
    SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
    SOURCE_TYPE_REPOSITORY,
    split_repo_identifier,
)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ScraperService:
    def __init__(self, client: GitHubGraphQLClient | None = None):
        self.client = client or GitHubGraphQLClient()

    def scrape_source(self, db: Session, source: Source) -> PipelineJob:
        if source.source_type not in {
            SOURCE_TYPE_REPOSITORY,
            SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
            SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
        }:
            raise ValueError(
                "Scraping only supports repository, organization discussions, "
                "and organization repositories"
            )

        now = utcnow()
        job = PipelineJob(
            job_type="scrape_discussions",
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
            created_since = now - timedelta(hours=settings.lookback_hours)
            if source.source_type == SOURCE_TYPE_ORGANIZATION_REPOSITORIES:
                repositories = self.client.fetch_discussion_enabled_repositories(
                    source.identifier
                )
                for repository in repositories:
                    owner, repo = split_repo_identifier(repository.name_with_owner)
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
                else:
                    owner = source.identifier
                    repo = source.identifier
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
            return job
        except Exception as exc:
            source.is_accessible = False
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = utcnow()
            db.commit()
            db.refresh(job)
            raise

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
            select(Discussion).where(
                Discussion.is_tracked.is_(True),
                Discussion.next_metric_update <= now,
            )
        ).all()

        try:
            affected_source_ids = set()
            for discussion in due_discussions:
                owner, repo = split_repo_identifier(discussion.repo_full_name)
                item = self.client.fetch_discussion_by_number(
                    owner,
                    repo,
                    discussion.discussion_number,
                    include_comments=False,
                )
                upsert_discussion(
                    db,
                    source_id=discussion.source_id,
                    item=item,
                    job_id=job.id,
                    now=now,
                    include_comments=False,
                )
                if discussion.source_id is not None:
                    affected_source_ids.add(discussion.source_id)
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
            return job
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)
            job.items_failed += 1
            job.finished_at = utcnow()
            db.commit()
            db.refresh(job)
            raise
