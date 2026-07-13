from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Discussion
from app.db.schemas import DiscussionRead
from app.db.session import get_db


router = APIRouter(prefix="/discussions", tags=["discussions"])


@router.get("", response_model=list[DiscussionRead])
def list_discussions(
    repo_full_name: str | None = None,
    source_id: int | None = None,
    metric_tier: str | None = None,
    is_tracked: bool | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = select(Discussion)
    if repo_full_name is not None:
        query = query.where(Discussion.repo_full_name == repo_full_name)
    if source_id is not None:
        query = query.where(Discussion.source_id == source_id)
    if metric_tier is not None:
        query = query.where(Discussion.metric_tier == metric_tier)
    if is_tracked is not None:
        query = query.where(Discussion.is_tracked.is_(is_tracked))

    return db.scalars(
        query.order_by(Discussion.discussion_created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/{discussion_id}", response_model=DiscussionRead)
def get_discussion(discussion_id: int, db: Session = Depends(get_db)):
    discussion = db.get(Discussion, discussion_id)
    if discussion is None:
        raise HTTPException(status_code=404, detail="Discussion not found")
    return discussion
