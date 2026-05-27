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


GDELT_REQUEST_DELAY = 5.0   # seconds between requests (GDELT enforces ~1 req/5s)
GDELT_MAX_RETRIES   = 4     # number of retries on 429 / empty response
GDELT_RETRY_BACKOFF = 15.0  # extra wait per retry attempt (seconds)

# GDELT blocks requests with the default python-requests User-Agent.
# Sending browser-like headers fixes empty / blocked responses.
GDELT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://api.gdeltproject.org/",
}


def fetch_timeline_volume(country_gdelt: str, theme_query: str, year: int) -> list[dict]:
    start, end = _build_timespan(year)
    params = {
        "query": f"sourcecountry:{country_gdelt} theme:{theme_query}",
        "mode": "timelinevol",
        "format": "json",
        "STARTDATETIME": start,
        "ENDDATETIME": end,
    }

    for attempt in range(1, GDELT_MAX_RETRIES + 1):
        try:
            resp = requests.get(GDELT_DOC_API, params=params, headers=GDELT_HEADERS, timeout=60)

            # 429 – rate limited: wait and retry
            if resp.status_code == 429:
                wait = GDELT_RETRY_BACKOFF * attempt
                logger.warning(
                    "GDELT 429 country=%s theme=%s year=%d – waiting %ss (attempt %d/%d)",
                    country_gdelt, theme_query, year, wait, attempt, GDELT_MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()

            # Guard against empty body (returned instead of JSON on soft rate-limit)
            if not resp.text.strip():
                wait = GDELT_RETRY_BACKOFF * attempt
                logger.warning(
                    "GDELT empty response country=%s theme=%s year=%d – waiting %ss (attempt %d/%d)",
                    country_gdelt, theme_query, year, wait, attempt, GDELT_MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            data = resp.json()
            # Response: {"timeline": [{"data": [{"value": N, "date": "YYYYMMDDHHMMSS"}, ...]}]}
            timeline = data.get("timeline", [])
            if not timeline:
                return []
            return timeline[0].get("data", [])

        except requests.RequestException as e:
            wait = GDELT_RETRY_BACKOFF * attempt
            logger.warning(
                "GDELT request error country=%s theme=%s year=%d: %s – waiting %ss (attempt %d/%d)",
                country_gdelt, theme_query, year, e, wait, attempt, GDELT_MAX_RETRIES,
            )
            time.sleep(wait)
        except ValueError as e:
            # JSON decode error – likely garbled response
            wait = GDELT_RETRY_BACKOFF * attempt
            logger.warning(
                "GDELT JSON parse error country=%s theme=%s year=%d: %s – waiting %ss (attempt %d/%d)",
                country_gdelt, theme_query, year, e, wait, attempt, GDELT_MAX_RETRIES,
            )
            time.sleep(wait)

    logger.error(
        "GDELT gave up country=%s theme=%s year=%d after %d attempts",
        country_gdelt, theme_query, year, GDELT_MAX_RETRIES,
    )
    return []


def _parse_month(date_str: str) -> Optional[int]:
    if len(date_str) >= 6:
        return int(date_str[4:6])
    return None


def ingest_gdelt(db: Session, year_start: int = 2015, year_end: int = 2023) -> int:
    from models import GdeltEvent, EventType, IngestionLog

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

                    time.sleep(GDELT_REQUEST_DELAY)  # GDELT rate limit: 1 req / 5s

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


