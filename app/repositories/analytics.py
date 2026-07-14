from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AnalyticsCache, Discussion, Source, SourceDiscussion


SOURCE_INTERVAL_MINUTES = {
    5: 30,
    4: 60,
    3: 120,
    2: 240,
    1: 480,
}


def source_score(
    total_discussions: int,
    total_comments: int,
    total_upvotes: int,
) -> float:
    return total_discussions * 2 + total_comments + total_upvotes * 0.5


def source_schedule_tier(score: float) -> int:
    if score >= 300:
        return 5
    if score >= 150:
        return 4
    if score >= 60:
        return 3
    if score >= 20:
        return 2
    return 1


def refresh_source_analytics_cache(
    db: Session,
    source: Source,
    now: datetime,
) -> AnalyticsCache:
    db.flush()

    total_discussions = db.scalar(
        select(func.count(SourceDiscussion.discussion_id)).where(
            SourceDiscussion.source_id == source.id
        )
    ) or 0
    total_comments = db.scalar(
        select(func.coalesce(func.sum(Discussion.comments_count), 0))
        .join(SourceDiscussion, SourceDiscussion.discussion_id == Discussion.id)
        .where(SourceDiscussion.source_id == source.id)
    ) or 0
    total_upvotes = db.scalar(
        select(func.coalesce(func.sum(Discussion.upvote_count), 0))
        .join(SourceDiscussion, SourceDiscussion.discussion_id == Discussion.id)
        .where(SourceDiscussion.source_id == source.id)
    ) or 0
    top_discussion_id = db.scalar(
        select(Discussion.id)
        .join(SourceDiscussion, SourceDiscussion.discussion_id == Discussion.id)
        .where(SourceDiscussion.source_id == source.id)
        .order_by(
            (Discussion.comments_count + Discussion.upvote_count).desc(),
            Discussion.discussion_updated_at.desc(),
        )
        .limit(1)
    )

    cache_date = now.date()
    cache = db.scalar(
        select(AnalyticsCache).where(
            AnalyticsCache.source_id == source.id,
            AnalyticsCache.date == cache_date,
        )
    )
    if cache is None:
        cache = AnalyticsCache(source_id=source.id, date=cache_date)
        db.add(cache)

    cache.total_discussions = total_discussions
    cache.total_comments = total_comments
    cache.total_upvotes = total_upvotes
    cache.avg_comments_per_discussion = (
        total_comments / total_discussions if total_discussions else 0
    )
    cache.top_discussion_id = top_discussion_id
    cache.growth_rate = _discussion_growth_rate(
        db,
        source.id,
        cache_date,
        total_discussions,
    )
    cache.cached_at = now

    score = source_score(total_discussions, total_comments, total_upvotes)
    source.schedule_tier = source_schedule_tier(score)
    source.next_scrape = now + timedelta(
        minutes=source.schedule_override_minutes
        or SOURCE_INTERVAL_MINUTES[source.schedule_tier]
    )

    return cache


def _discussion_growth_rate(
    db: Session,
    source_id: int,
    cache_date: date,
    total_discussions: int,
) -> float:
    previous = db.scalar(
        select(AnalyticsCache)
        .where(
            AnalyticsCache.source_id == source_id,
            AnalyticsCache.date < cache_date,
        )
        .order_by(AnalyticsCache.date.desc())
        .limit(1)
    )
    if previous is None or previous.total_discussions == 0:
        return 0

    return (
        (total_discussions - previous.total_discussions)
        / previous.total_discussions
        * 100
    )
