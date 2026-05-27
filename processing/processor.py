"""
Data processing module.
Computes annual event totals and GDP-event correlations per country.
"""
import logging
import os
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@db:5432/gdp_events")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


def compute_correlations(year_start: int = 2015, year_end: int = 2023) -> int:
    """Pearson correlation between annual GDP and annual event counts per country/event_type."""
    db = Session()
    stored = 0
    try:
        countries = [r[0] for r in db.execute(text("SELECT code FROM countries")).fetchall()]
        event_types = db.execute(text("SELECT id, theme_code FROM event_types")).fetchall()

        for country in countries:
            gdp_rows = db.execute(
                text("SELECT year, gdp_usd FROM gdp_data WHERE country_code=:c AND year BETWEEN :s AND :e ORDER BY year"),
                {"c": country, "s": year_start, "e": year_end},
            ).fetchall()
            if len(gdp_rows) < 3:
                continue
            gdp_by_year = {r[0]: float(r[1]) for r in gdp_rows if r[1] is not None}

            for et_id, et_code in event_types:
                event_rows = db.execute(
                    text("""
                        SELECT year, SUM(article_count) as total
                        FROM gdelt_events
                        WHERE country_code=:c AND event_type_id=:et
                          AND year BETWEEN :s AND :e
                        GROUP BY year ORDER BY year
                    """),
                    {"c": country, "et": et_id, "s": year_start, "e": year_end},
                ).fetchall()
                if len(event_rows) < 3:
                    continue

                ev_by_year = {r[0]: float(r[1]) for r in event_rows}
                common_years = sorted(set(gdp_by_year) & set(ev_by_year))
                if len(common_years) < 3:
                    continue

                gdp_vals = [gdp_by_year[y] for y in common_years]
                ev_vals = [ev_by_year[y] for y in common_years]
                corr = _pearson(gdp_vals, ev_vals)

                db.execute(
                    text("""
                        INSERT INTO analysis_results
                            (country_code, event_type_id, year_start, year_end, correlation_coefficient, sample_size, calculated_at)
                        VALUES (:c, :et, :s, :e, :corr, :n, :now)
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "c": country, "et": et_id, "s": year_start, "e": year_end,
                        "corr": round(corr, 6), "n": len(common_years), "now": datetime.utcnow(),
                    },
                )
                stored += 1

        db.commit()
        logger.info("Correlation computation complete: %d results", stored)
    except Exception:
        db.rollback()
        logger.exception("Correlation computation failed")
    finally:
        db.close()
    return stored


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    denom_x = sum((xi - mx) ** 2 for xi in x) ** 0.5
    denom_y = sum((yi - my) ** 2 for yi in y) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return num / (denom_x * denom_y)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    compute_correlations()
