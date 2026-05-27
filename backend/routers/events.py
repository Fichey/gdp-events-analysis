from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from database import get_db
from models import GdeltEvent, EventType, Country
from schemas import GdeltEventOut, EventTypeOut

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/types", response_model=list[EventTypeOut])
def list_event_types(db: Session = Depends(get_db)):
    """Returns all event type categories."""
    return db.query(EventType).all()


@router.get("/{country_code}", response_model=list[GdeltEventOut])
def get_events(
    country_code: str,
    event_type: Optional[str] = Query(None, description="Filter by theme_code e.g. PROTEST"),
    year_start: Optional[int] = Query(None),
    year_end: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns GDELT event article counts for a country, grouped by year and type."""
    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    q = (
        db.query(
            GdeltEvent.country_code,
            GdeltEvent.year,
            func.sum(GdeltEvent.article_count).label("article_count"),
            EventType.theme_code,
            EventType.theme_name,
        )
        .join(EventType, GdeltEvent.event_type_id == EventType.id)
        .filter(GdeltEvent.country_code == country_code.upper())
    )
    if event_type:
        q = q.filter(EventType.theme_code == event_type.upper())
    if year_start:
        q = q.filter(GdeltEvent.year >= year_start)
    if year_end:
        q = q.filter(GdeltEvent.year <= year_end)

    rows = q.group_by(
        GdeltEvent.country_code, GdeltEvent.year, EventType.theme_code, EventType.theme_name
    ).order_by(GdeltEvent.year).all()

    return [
        GdeltEventOut(
            country_code=r.country_code,
            year=r.year,
            article_count=r.article_count,
            theme_code=r.theme_code,
            theme_name=r.theme_name,
        )
        for r in rows
    ]
