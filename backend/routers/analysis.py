from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models import AnalysisResult, EventType
from schemas import AnalysisResultOut

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.get("/correlations", response_model=list[AnalysisResultOut])
def get_correlations(
    country_code: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    year_start: Optional[int] = Query(None),
    year_end: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Returns Pearson correlation coefficients between annual GDP and event counts.

    When year_start / year_end are supplied the correlation is computed
    on-the-fly using PostgreSQL's corr() aggregate directly from raw data —
    no need to re-run the processing service.

    When neither is supplied the endpoint falls back to the pre-computed
    rows in analysis_results (populated by the background processor).
    """
    if year_start is not None or year_end is not None:
        ys = year_start if year_start is not None else 2010
        ye = year_end   if year_end   is not None else 2024

        params: dict = {"ys": ys, "ye": ye}
        where_country = ""
        where_theme   = ""
        if country_code:
            where_country = "AND e.country_code = :country_code"
            params["country_code"] = country_code.upper()
        if event_type:
            where_theme = "AND et.theme_code = :event_type"
            params["event_type"] = event_type.upper()

        sql = f"""
            SELECT
                e.country_code,
                et.theme_code,
                et.theme_name,
                :ys          AS year_start,
                :ye          AS year_end,
                corr(g.gdp_usd::float, e.total_events::float) AS correlation_coefficient,
                count(*)::int AS sample_size
            FROM (
                SELECT country_code, event_type_id, year,
                       SUM(article_count)::float AS total_events
                FROM gdelt_events
                WHERE year BETWEEN :ys AND :ye
                GROUP BY country_code, event_type_id, year
            ) e
            JOIN gdp_data g
              ON g.country_code = e.country_code
             AND g.year         = e.year
             AND g.gdp_usd IS NOT NULL
            JOIN event_types et ON et.id = e.event_type_id
            WHERE 1 = 1
            {where_country}
            {where_theme}
            GROUP BY e.country_code, e.event_type_id, et.theme_code, et.theme_name
            HAVING count(*) >= 3
               AND corr(g.gdp_usd::float, e.total_events::float) IS NOT NULL
            ORDER BY e.country_code, et.theme_code
        """

        rows = db.execute(text(sql), params).fetchall()
        return [
            AnalysisResultOut(
                country_code=row[0],
                theme_code=row[1],
                theme_name=row[2],
                year_start=row[3],
                year_end=row[4],
                correlation_coefficient=round(float(row[5]), 6),
                sample_size=row[6],
            )
            for row in rows
        ]

    # ── fallback: pre-computed results ────────────────────────────────────────
    q = (
        db.query(AnalysisResult, EventType.theme_code, EventType.theme_name)
        .join(EventType, AnalysisResult.event_type_id == EventType.id)
    )
    if country_code:
        q = q.filter(AnalysisResult.country_code == country_code.upper())
    if event_type:
        q = q.filter(EventType.theme_code == event_type.upper())

    results = []
    for ar, theme_code, theme_name in q.order_by(AnalysisResult.country_code).all():
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
