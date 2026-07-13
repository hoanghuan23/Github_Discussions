from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Source
from app.db.schemas import ScrapeResult, SourceCreate, SourceRead
from app.db.session import get_db
from app.services.scraper import ScraperService
from app.services.source_parser import (
    SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
    SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
    SOURCE_TYPE_REPOSITORY,
    parse_source,
)


router = APIRouter(prefix="/sources", tags=["sources"])


@router.post("", response_model=ScrapeResult)
def create_source(payload: SourceCreate, db: Session = Depends(get_db)):
    try:
        source_type, identifier = parse_source(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source = db.scalar(
        select(Source).where(
            Source.source_type == source_type,
            Source.identifier == identifier,
        )
    )
    if source is None:
        now = datetime.now(UTC).replace(tzinfo=None)
        source = Source(
            source_type=source_type,
            identifier=identifier,
            is_active=True,
            is_accessible=True,
            include_comments=payload.include_comments,
            created_at=now,
        )
        db.add(source)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            source = db.scalar(
                select(Source).where(
                    Source.source_type == source_type,
                    Source.identifier == identifier,
                )
            )
        else:
            db.refresh(source)
    else:
        source.include_comments = payload.include_comments
        db.commit()
        db.refresh(source)

    if source.source_type in {
        SOURCE_TYPE_REPOSITORY,
        SOURCE_TYPE_ORGANIZATION_DISCUSSIONS,
        SOURCE_TYPE_ORGANIZATION_REPOSITORIES,
    }:
        try:
            job = ScraperService().scrape_source(db, source)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        job = None

    db.refresh(source)
    return ScrapeResult(source=source, job=job)


@router.get("", response_model=list[SourceRead])
def list_sources(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Source).order_by(Source.id.desc()).limit(limit).offset(offset)
    ).all()


@router.get("/{source_id}", response_model=SourceRead)
def get_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("/{source_id}/scrape", response_model=ScrapeResult)
def scrape_source(source_id: int, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    try:
        job = ScraperService().scrape_source(db, source)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.refresh(source)
    return ScrapeResult(source=source, job=job)
