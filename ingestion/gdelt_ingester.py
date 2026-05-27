"""
GDELT 2.0 Document API ingester.
Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
No API key required.

Uses timeline volume mode to count article mentions of events
(protest, military, election, economy, disaster, crime) per country per month.
"""
import logging
import time
from datetime import datetime
from typing import Optional

import requests
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT country codes (FIPS 2-letter used in sourcecountry filter)
GDELT_COUNTRY_MAP = {
    "POL": "PL", "DEU": "GM", "USA": "US", "FRA": "FR",
    "BRA": "BR", "IND": "IN", "CHN": "CH", "JPN": "JA",
    "GBR": "UK", "ITA": "IT",
}

# GDELT themes mapped to our event type codes
THEME_QUERY_MAP = {
    "PROTEST":  "PROTEST",
    "MILITARY": "KILL OR ARMED_CONFLICT",
    "ELECTION": "ELECTION",
    "ECONOMY":  "ECON_BANKRUPTCY OR ECON_RECESSION",
    "DISASTER": "NATURAL_DISASTER OR ENV_DISASTER",
    "CRIME":    "CRIME_MURDER OR CRIMEVIOLENCE",
}


def _build_timespan(year: int) -> tuple[str, str]:
    return f"{year}0101000000", f"{year}1231235959"


def fetch_timeline_volume(country_gdelt: str, theme_query: str, year: int) -> list[dict]:
    start, end = _build_timespan(year)
    params = {
        "query": f"sourcecountry:{country_gdelt} theme:{theme_query}",
        "mode": "timelinevol",
        "format": "json",
        "STARTDATETIME": start,
        "ENDDATETIME": end,
    }
    try:
        resp = requests.get(GDELT_DOC_API, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        # Response: {"timeline": [{"series": [{"value": N, "date": "YYYYMMDDHHMMSS"}, ...]}]}
        timeline = data.get("timeline", [])
        if not timeline:
            return []
        return timeline[0].get("data", [])
    except (requests.RequestException, ValueError) as e:
        logger.warning("GDELT request failed country=%s theme=%s year=%d: %s", country_gdelt, theme_query, year, e)
        return []


def _parse_month(date_str: str) -> Optional[int]:
    if len(date_str) >= 6:
        return int(date_str[4:6])
    return None


def ingest_gdelt(db: Session, year_start: int = 2015, year_end: int = 2023) -> int:
    from ingestion.models import GdeltEvent, EventType, IngestionLog

    log = IngestionLog(source="gdelt", status="running")
    db.add(log)
    db.commit()

    event_types = {et.theme_code: et for et in db.query(EventType).all()}
    total = 0

    try:
        for code3, code_gdelt in GDELT_COUNTRY_MAP.items():
            for theme_code, theme_query in THEME_QUERY_MAP.items():
                et = event_types.get(theme_code)
                if not et:
                    continue

                for year in range(year_start, year_end + 1):
                    series = fetch_timeline_volume(code_gdelt, theme_query, year)

                    monthly: dict[int, int] = {}
                    for point in series:
                        month = _parse_month(point.get("date", ""))
                        if month:
                            monthly[month] = monthly.get(month, 0) + int(point.get("value", 0))

                    for month, count in monthly.items():
                        existing = db.query(GdeltEvent).filter_by(
                            country_code=code3,
                            event_type_id=et.id,
                            year=year,
                            month=month,
                        ).first()
                        if existing:
                            existing.article_count = count
                        else:
                            db.add(GdeltEvent(
                                country_code=code3,
                                event_type_id=et.id,
                                year=year,
                                month=month,
                                article_count=count,
                            ))
                        total += 1

                    time.sleep(1.0)  # GDELT rate limit: ~1 req/sec

        db.commit()
        log.status = "success"
        log.records_fetched = total
    except Exception as e:
        db.rollback()
        log.status = "error"
        log.error_message = str(e)
        logger.exception("GDELT ingestion failed")
    finally:
        log.finished_at = datetime.utcnow()
        db.commit()

    logger.info("GDELT ingestion complete: %d records", total)
    return total


