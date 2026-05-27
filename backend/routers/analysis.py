from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models import AnalysisResult, EventType
from schemas import AnalysisResultOut

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.get("/correlations", response_model=list[AnalysisResultOut])
def get_correlations(
    country_code: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Returns pre-computed Pearson correlation coefficients between GDP and event counts."""
    q = (
        db.query(
            AnalysisResult,
            EventType.theme_code,
            EventType.theme_name,
        )
        .join(EventType, AnalysisResult.event_type_id == EventType.id)
    )
    if country_code:
        q = q.filter(AnalysisResult.country_code == country_code.upper())
    if event_type:
        q = q.filter(EventType.theme_code == event_type.upper())

    rows = q.order_by(AnalysisResult.country_code).all()
    results = []
    for ar, theme_code, theme_name in rows:
        if ar.correlation_coefficient is None:
            continue
        results.append(
            AnalysisResultOut(
                country_code=ar.country_code,
                theme_code=theme_code,
                theme_name=theme_name,
                year_start=ar.year_start,
                year_end=ar.year_end,
                correlation_coefficient=float(ar.correlation_coefficient),
                sample_size=ar.sample_size or 0,
            )
        )
    return results


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Returns record counts for quick status check."""
    from sqlalchemy import text
    counts = {}
    for table in ("countries", "gdp_data", "gdelt_events", "analysis_results"):
        row = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        counts[table] = row
    return counts
