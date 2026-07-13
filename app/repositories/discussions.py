from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    Discussion,
    DiscussionComment,
    DiscussionMetric,
    SourceDiscussion,
)
from app.services.github_client import GitHubDiscussion


def metric_tier(comments_count: int, upvote_count: int) -> str:
    score = comments_count + upvote_count
    if score >= 100:
        return "hot"
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    if score >= 5:
        return "low"
    return "very_low"


def upsert_discussion(
    db: Session,
    source_id: int | None,
    item: GitHubDiscussion,
    job_id: int | None,
    now: datetime,
    include_comments: bool,
) -> tuple[Discussion, bool]:
    discussion = db.scalar(
        select(Discussion).where(
            Discussion.github_discussion_id == item.github_discussion_id
        )
    )
    if discussion is None:
        discussion = db.scalar(
            select(Discussion).where(
                Discussion.repo_full_name == item.repo_full_name,
                Discussion.discussion_number == item.discussion_number,
            )
        )

    created = discussion is None
    next_metric_update = now + timedelta(
        minutes=settings.default_metric_interval_minutes
    )

    if created:
        discussion = Discussion(
            github_discussion_id=item.github_discussion_id,
            source_id=source_id,
            repo_full_name=item.repo_full_name,
            discussion_number=item.discussion_number,
            title=item.title,
            author_login=item.author_login,
            category_name=item.category_name,
            comments_count=item.comments_count,
            upvote_count=item.upvote_count,
            html_url=item.html_url,
            discussion_created_at=item.discussion_created_at,
            discussion_updated_at=item.discussion_updated_at,
            created_at=now,
            is_tracked=True,
            is_deleted=False,
            last_metric_update=now,
            next_metric_update=next_metric_update,
            metric_tier=metric_tier(item.comments_count, item.upvote_count),
        )
        db.add(discussion)
        db.flush()
    else:
        discussion.source_id = discussion.source_id or source_id
        discussion.title = item.title
        discussion.author_login = item.author_login
        discussion.category_name = item.category_name
        discussion.comments_count = item.comments_count
        discussion.upvote_count = item.upvote_count
        discussion.html_url = item.html_url
        discussion.discussion_updated_at = item.discussion_updated_at
        discussion.is_deleted = False
        discussion.last_metric_update = now
        discussion.next_metric_update = next_metric_update
        discussion.metric_tier = metric_tier(item.comments_count, item.upvote_count)

    if source_id is not None:
        link = db.get(
            SourceDiscussion,
            {"source_id": source_id, "discussion_id": discussion.id},
        )
        if link is None:
            db.add(
                SourceDiscussion(
                    source_id=source_id,
                    discussion_id=discussion.id,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            link.last_seen_at = now

    db.add(
        DiscussionMetric(
            discussion_id=discussion.id,
            comments_count=item.comments_count,
            upvote_count=item.upvote_count,
            recorded_at=now,
            job_id=job_id,
        )
    )

    if include_comments:
        upsert_comments(db, discussion.id, item, now)

    return discussion, created


def upsert_comments(
    db: Session,
    discussion_id: int,
    item: GitHubDiscussion,
    now: datetime,
) -> None:
    for comment in item.comments:
        existing = db.scalar(
            select(DiscussionComment).where(
                DiscussionComment.github_comment_id == comment.github_comment_id
            )
        )
        if existing is None:
            db.add(
                DiscussionComment(
                    discussion_id=discussion_id,
                    github_comment_id=comment.github_comment_id,
                    author_login=comment.author_login,
                    comment_body=comment.comment_body,
                    html_url=comment.html_url,
                    comment_created_at=comment.comment_created_at,
                    created_at=now,
                )
            )
        else:
            existing.author_login = comment.author_login
            existing.comment_body = comment.comment_body
            existing.html_url = comment.html_url
            existing.comment_created_at = comment.comment_created_at
