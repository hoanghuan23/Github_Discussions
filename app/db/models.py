from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ("
            "'repository', "
            "'organization_repositories', "
            "'organization_discussions', "
            "'category'"
            ")",
            name="ck_sources_source_type",
        ),
        UniqueConstraint("source_type", "identifier"),
    )

    id = Column(Integer, primary_key=True)
    source_type = Column(String(40), nullable=False)
    identifier = Column(String(300), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_accessible = Column(Boolean, nullable=False, default=True)
    include_comments = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False)
    last_scraped = Column(DateTime)
    next_scrape = Column(DateTime)
    schedule_tier = Column(Integer)
    schedule_override_minutes = Column(Integer)

    discussions = relationship("Discussion", back_populates="source")
    jobs = relationship("PipelineJob", back_populates="source")


class Discussion(Base):
    __tablename__ = "discussions"
    __table_args__ = (
        UniqueConstraint("github_discussion_id"),
        UniqueConstraint("repo_full_name", "discussion_number"),
        CheckConstraint(
            "metric_tier IN ('hot', 'high', 'medium', 'low', 'very_low', 'bootstrap')",
            name="ck_discussions_metric_tier",
        ),
    )

    id = Column(Integer, primary_key=True)
    github_discussion_id = Column(String(100), nullable=False)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    repo_full_name = Column(String(300), nullable=False)
    discussion_number = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    author_login = Column(String(100))
    category_name = Column(String(200))
    comments_count = Column(Integer, nullable=False, default=0)
    upvote_count = Column(Integer, nullable=False, default=0)
    html_url = Column(Text, nullable=False)
    discussion_created_at = Column(DateTime, nullable=False)
    discussion_updated_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)
    is_tracked = Column(Boolean, nullable=False, default=True)
    tracking_until = Column(DateTime)
    is_deleted = Column(Boolean, nullable=False, default=False)
    last_metric_update = Column(DateTime)
    next_metric_update = Column(DateTime)
    metric_tier = Column(String(20), nullable=False, default="bootstrap")

    source = relationship("Source", back_populates="discussions")
    metrics = relationship("DiscussionMetric", back_populates="discussion")
    comments = relationship("DiscussionComment", back_populates="discussion")


class SourceDiscussion(Base):
    __tablename__ = "source_discussions"

    source_id = Column(
        Integer,
        ForeignKey("sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    discussion_id = Column(
        Integer,
        ForeignKey("discussions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    first_seen_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False)


class AnalyticsCache(Base):
    __tablename__ = "analytics_cache"
    __table_args__ = (UniqueConstraint("source_id", "date"),)

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    total_discussions = Column(Integer, nullable=False, default=0)
    total_comments = Column(Integer, nullable=False, default=0)
    total_upvotes = Column(Integer, nullable=False, default=0)
    avg_comments_per_discussion = Column(Float, nullable=False, default=0)
    top_discussion_id = Column(Integer, ForeignKey("discussions.id", ondelete="SET NULL"))
    growth_rate = Column(Float, nullable=False, default=0)
    cached_at = Column(DateTime, nullable=False)


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('scrape_discussions', 'scrape_new_discussions', "
            "'update_metrics', 'scrape_comments', 'sync_repos')",
            name="ck_pipeline_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_pipeline_jobs_status",
        ),
    )

    id = Column(Integer, primary_key=True)
    job_type = Column(String(30), nullable=False, default="scrape_discussions")
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    status = Column(String(10), nullable=False, default="pending")
    discussions_found = Column(Integer, nullable=False, default=0)
    discussions_new = Column(Integer, nullable=False, default=0)
    discussions_updated = Column(Integer, nullable=False, default=0)
    items_failed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False)

    source = relationship("Source", back_populates="jobs")


class DiscussionMetric(Base):
    __tablename__ = "discussion_metrics"

    id = Column(Integer, primary_key=True)
    discussion_id = Column(
        Integer,
        ForeignKey("discussions.id", ondelete="CASCADE"),
        nullable=False,
    )
    comments_count = Column(Integer, nullable=False, default=0)
    upvote_count = Column(Integer, nullable=False, default=0)
    recorded_at = Column(DateTime, nullable=False)
    job_id = Column(Integer, ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))

    discussion = relationship("Discussion", back_populates="metrics")


class DiscussionComment(Base):
    __tablename__ = "discussion_comments"
    __table_args__ = (UniqueConstraint("github_comment_id"),)

    id = Column(Integer, primary_key=True)
    discussion_id = Column(
        Integer,
        ForeignKey("discussions.id", ondelete="CASCADE"),
        nullable=False,
    )
    github_comment_id = Column(String(100), nullable=False)
    author_login = Column(String(100))
    comment_body = Column(Text)
    html_url = Column(Text)
    comment_created_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False)

    discussion = relationship("Discussion", back_populates="comments")


class PipelineLog(Base):
    __tablename__ = "pipeline_logs"
    __table_args__ = (
        CheckConstraint(
            "log_level IN ('ERROR', 'WARNING')",
            name="ck_pipeline_logs_log_level",
        ),
    )

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("pipeline_jobs.id", ondelete="SET NULL"))
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    log_level = Column(String(20), nullable=False, default="ERROR")
    message = Column(Text, nullable=False)
    error_type = Column(String(100))
    error_details = Column(Text)
    created_at = Column(DateTime, nullable=False)
