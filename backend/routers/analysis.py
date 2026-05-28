from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from models import AnalysisResult, EventType
from schemas import AnalysisResultOut, LagResultOut

router = APIRouter(prefix="/analysis", tags=["Analysis"])

# ── helpers ───────────────────────────────────────────────────────────────────

def _metric_sql(metric: str) -> tuple[str, str]:
    """Return (gdp_column_expr, gdp_null_filter) for the chosen metric."""
    if metric == "growth":
        return "g.gdp_growth_rate::float", "AND g.gdp_growth_rate IS NOT NULL"
    return "g.gdp_usd::float", "AND g.gdp_usd IS NOT NULL"


# ── /correlations ─────────────────────────────────────────────────────────────

@router.get("/correlations", response_model=list[AnalysisResultOut])
def get_correlations(
    country_code: Optional[str] = Query(None),
    event_type:   Optional[str] = Query(None),
    year_start:   Optional[int] = Query(None),
    year_end:     Optional[int] = Query(None),
    metric: str = Query("gdp", description="'gdp' = absolute GDP value | 'growth' = GDP growth rate %"),
    db: Session = Depends(get_db),
):
    """
    Pearson correlation between GDP (or GDP growth rate) and event counts.
    Computed on-the-fly when year_start/year_end are provided;
    falls back to pre-computed analysis_results otherwise.
    """
    if year_start is not None or year_end is not None:
        ys = year_start or 2010
        ye = year_end   or 2024
        gdp_col, gdp_filter = _metric_sql(metric)

        params: dict = {"ys": ys, "ye": ye}
        wc, wt = "", ""
        if country_code:
            wc = "AND e.country_code = :country_code"
            params["country_code"] = country_code.upper()
        if event_type:
            wt = "AND et.theme_code = :event_type"
            params["event_type"] = event_type.upper()

        sql = f"""
            SELECT e.country_code, et.theme_code, et.theme_name,
                   :ys AS year_start, :ye AS year_end,
                   corr({gdp_col}, e.total_events) AS corr,
                   count(*)::int AS n
            FROM (
                SELECT country_code, event_type_id, year,
                       SUM(article_count)::float AS total_events
                FROM gdelt_events
                WHERE year BETWEEN :ys AND :ye
                GROUP BY country_code, event_type_id, year
            ) e
            JOIN gdp_data g ON g.country_code = e.country_code
                            AND g.year = e.year
                            {gdp_filter}
            JOIN event_types et ON et.id = e.event_type_id
            WHERE 1=1 {wc} {wt}
            GROUP BY e.country_code, e.event_type_id, et.theme_code, et.theme_name
            HAVING count(*) >= 3
               AND corr({gdp_col}, e.total_events) IS NOT NULL
            ORDER BY e.country_code, et.theme_code
        """
        rows = db.execute(text(sql), params).fetchall()
        return [
            AnalysisResultOut(
                country_code=r[0], theme_code=r[1], theme_name=r[2],
                year_start=r[3], year_end=r[4],
                correlation_coefficient=round(float(r[5]), 6),
                sample_size=r[6],
            )
            for r in rows
        ]

    # fallback: pre-computed
    q = (
        db.query(AnalysisResult, EventType.theme_code, EventType.theme_name)
        .join(EventType, AnalysisResult.event_type_id == EventType.id)
    )
    if country_code:
        q = q.filter(AnalysisResult.country_code == country_code.upper())
    if event_type:
        q = q.filter(EventType.theme_code == event_type.upper())

    results = []
    for ar, tc, tn in q.order_by(AnalysisResult.country_code).all():
        if ar.correlation_coefficient is None:
            continue
        results.append(AnalysisResultOut(
            country_code=ar.country_code, theme_code=tc, theme_name=tn,
            year_start=ar.year_start, year_end=ar.year_end,
            correlation_coefficient=float(ar.correlation_coefficient),
            sample_size=ar.sample_size or 0,
        ))
    return results


# ── /correlations/lag ─────────────────────────────────────────────────────────

@router.get("/correlations/lag", response_model=list[LagResultOut])
def get_lag_correlations(
    country_code: Optional[str] = Query(None),
    event_type:   Optional[str] = Query(None),
    year_start:   Optional[int] = Query(None),
    year_end:     Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Pearson correlation between GDP growth rate and event counts for
    time lags -2 to +2 years (uses GDP growth rate, not absolute GDP).

    Lag > 0: events precede GDP change  → events may predict GDP.
    Lag < 0: events follow GDP change   → GDP may trigger events.
    Lag = 0: contemporaneous correlation.
    """
    ys = year_start or 2010
    ye = year_end   or 2024
    results = []

    for lag in range(-2, 3):
        params: dict = {"ys": ys, "ye": ye}
        wc, wt = "", ""
        if country_code:
            wc = "AND e.country_code = :country_code"
            params["country_code"] = country_code.upper()
        if event_type:
            wt = "AND et.theme_code = :event_type"
            params["event_type"] = event_type.upper()

        lag_year = f"e.year + {lag}" if lag else "e.year"

        sql = f"""
            SELECT e.country_code, et.theme_code, et.theme_name,
                   corr(g.gdp_growth_rate::float, e.total_events) AS corr,
                   count(*)::int AS n
            FROM (
                SELECT country_code, event_type_id, year,
                       SUM(article_count)::float AS total_events
                FROM gdelt_events
                WHERE year BETWEEN :ys AND :ye
                GROUP BY country_code, event_type_id, year
            ) e
            JOIN gdp_data g ON g.country_code = e.country_code
                            AND g.year = {lag_year}
                            AND g.gdp_growth_rate IS NOT NULL
            JOIN event_types et ON et.id = e.event_type_id
            WHERE 1=1 {wc} {wt}
            GROUP BY e.country_code, e.event_type_id, et.theme_code, et.theme_name
            HAVING count(*) >= 3
               AND corr(g.gdp_growth_rate::float, e.total_events) IS NOT NULL
            ORDER BY e.country_code, et.theme_code
        """
        for r in db.execute(text(sql), params).fetchall():
            results.append(LagResultOut(
                country_code=r[0], theme_code=r[1], theme_name=r[2],
                lag=lag,
                correlation_coefficient=round(float(r[3]), 6),
                sample_size=r[4],
            ))

    return results


# ── /anomalies ────────────────────────────────────────────────────────────────

@router.get("/anomalies")
def get_anomalies(
    country_code: Optional[str] = Query(None),
    event_type:   Optional[str] = Query(None),
    year_start:   Optional[int] = Query(None),
    year_end:     Optional[int] = Query(None),
    threshold:    float         = Query(2.0, description="Z-score threshold (default 2.0 = 2σ)"),
    db: Session = Depends(get_db),
):
    """
    Detect months where article_count exceeds the historical mean by
    more than `threshold` standard deviations (z-score > threshold).
    Stats are computed globally (not per year range) so spikes are
    measured against the full baseline.  Returns top 50 by z-score.
    """
    ys = year_start or 2010
    ye = year_end   or 2025
    params: dict = {"ys": ys, "ye": ye, "threshold": threshold}
    wc, wt = "", ""
    if country_code:
        wc = "AND e.country_code = :country_code"
        params["country_code"] = country_code.upper()
    if event_type:
        wt = "AND et.theme_code = :event_type"
        params["event_type"] = event_type.upper()

    sql = f"""
        WITH stats AS (
            SELECT country_code, event_type_id,
                   AVG(article_count::float)    AS mean_count,
                   STDDEV(article_count::float) AS std_count
            FROM gdelt_events
            GROUP BY country_code, event_type_id
        )
        SELECT e.country_code, et.theme_code, et.theme_name,
               e.year, e.month, e.article_count,
               ROUND(s.mean_count::numeric, 1) AS mean_count,
               ROUND(((e.article_count - s.mean_count)
                      / NULLIF(s.std_count, 0))::numeric, 2) AS z_score
        FROM gdelt_events e
        JOIN stats s ON s.country_code = e.country_code
                     AND s.event_type_id = e.event_type_id
        JOIN event_types et ON et.id = e.event_type_id
        WHERE e.year BETWEEN :ys AND :ye
          AND s.std_count > 0
          AND (e.article_count - s.mean_count) / s.std_count > :threshold
          {wc} {wt}
        ORDER BY z_score DESC
        LIMIT 50
    """
    rows = db.execute(text(sql), params).fetchall()
    return [
        {
            "country_code": r[0], "theme_code": r[1], "theme_name": r[2],
            "year": r[3], "month": r[4], "article_count": r[5],
            "mean_count": float(r[6]), "z_score": float(r[7]),
        }
        for r in rows
    ]


# ── /summary ──────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Record counts for quick status check."""
    counts = {}
    for table in ("countries", "gdp_data", "gdelt_events", "analysis_results"):
        counts[table] = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    return counts
