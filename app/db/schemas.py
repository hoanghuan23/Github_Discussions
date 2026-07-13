from datetime import datetime

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    url: str = Field(..., examples=["https://github.com/vercel/next.js/discussions"])
    include_comments: bool = False


class SourceRead(BaseModel):
    id: int
    source_type: str
    identifier: str
    is_active: bool
    is_accessible: bool
    include_comments: bool
    created_at: datetime
    last_scraped: datetime | None
    next_scrape: datetime | None
    schedule_tier: int | None
    schedule_override_minutes: int | None

    model_config = {"from_attributes": True}


class DiscussionRead(BaseModel):
    id: int
    github_discussion_id: str
    source_id: int | None
    repo_full_name: str
    discussion_number: int
    title: str
    author_login: str | None
    category_name: str | None
    comments_count: int
    upvote_count: int
    html_url: str
    discussion_created_at: datetime
    discussion_updated_at: datetime
    created_at: datetime
    is_tracked: bool
    tracking_until: datetime | None
    is_deleted: bool
    last_metric_update: datetime | None
    next_metric_update: datetime | None
    metric_tier: str

    model_config = {"from_attributes": True}


class JobRead(BaseModel):
    id: int
    job_type: str
    source_id: int | None
    status: str
    discussions_found: int
    discussions_new: int
    discussions_updated: int
    items_failed: int
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScrapeResult(BaseModel):
    source: SourceRead
    job: JobRead | None
