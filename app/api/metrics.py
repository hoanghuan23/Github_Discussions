from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.schemas import JobRead
from app.db.session import get_db
from app.services.scraper import ScraperService


router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.post("/due/run", response_model=JobRead)
def run_due_metrics(db: Session = Depends(get_db)):
    try:
        return ScraperService().update_due_metrics(db)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
