from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PipelineJob
from app.db.schemas import JobRead
from app.db.session import get_db


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobRead])
def list_jobs(
    source_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = select(PipelineJob)
    if source_id is not None:
        query = query.where(PipelineJob.source_id == source_id)
    if status is not None:
        query = query.where(PipelineJob.status == status)

    return db.scalars(
        query.order_by(PipelineJob.created_at.desc()).limit(limit).offset(offset)
    ).all()


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
