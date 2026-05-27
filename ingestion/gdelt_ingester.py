"""
GDELT 2.0 Document API ingester.
Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
No API key required.

Fetches timeline volume (article-mention counts) for 6 event themes across
10 countries over the configured year range — one request per (country, theme)
covering the full range, then splits results by year+month locally.

This approach uses 60 requests total (10 countries × 6 themes) instead of
540 (× 9 years), staying well within GDELT rate limits.
"""
import logging
import time
from datetime import datetime
from typing import Optional

import requests                          # fallback / WorldBank (no Cloudflare)
from curl_cffi import requests as cf    # Chrome TLS impersonation for GDELT
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Delay between consecutive GDELT requests (seconds).
# GDELT recommends no more than 1 req / 5 s from a single IP.
GDELT_REQUEST_DELAY = 8.0

# Retry settings for transient errors (429, empty body, parse failure).
GDELT_MAX_RETRIES   = 5
GDELT_RETRY_BACKOFF = 20.0   # wait = BACKOFF × attempt_number

# GDELT blocks the default "python-requests/x.y" User-Agent.
# A browser-like UA string is required to receive JSON responses.
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

# GDELT uses FIPS-10 2-letter country codes (not ISO-3166-1 alpha-2).
GDELT_COUNTRY_MAP = {
    "POL": "PL",
    "DEU": "GM",
    "USA": "US",
    "FRA": "FR",
    "BRA": "BR",
    "IND": "IN",
    "CHN": "CH",
    "JPN": "JA",
    "GBR": "UK",
    "ITA": "IT",
}

# Maps our internal theme_code → GDELT query expression.
THEME_QUERY_MAP = {
    "PROTEST":  "PROTEST",
    "MILITARY": "KILL OR ARMED_CONFLICT",
    "ELECTION": "ELECTION",
    "ECONOMY":  "ECON_BANKRUPTCY OR ECON_RECESSION",
    "DISASTER": "NATURAL_DISASTER OR ENV_DISASTER",
    "CRIME":    "CRIME_MURDER OR CRIMEVIOLENCE",
}


def _dt(year: int, month: int = 1, day: int = 1) -> str:
    """Format a date as GDELT STARTDATETIME / ENDDATETIME string."""
    return f"{year}{month:02d}{day:02d}000000"


def fetch_timeline_range(
    country_gdelt: str,
    theme_query: str,
    year_start: int,
    year_end: int,
) -> list:
    """
    Fetch weekly article-count timeline from GDELT for the full year range.
    Returns a list of {"date": "YYYYMMDDHHMMSS", "value": float} dicts,
    or an empty list on permanent failure.

    One HTTP request covers all years — far fewer total calls than per-year fetching.
    """
    params = {
        "query": f"sourcecountry:{country_gdelt} theme:{theme_query}",
        "mode": "timelinevol",
        "format": "json",
        "STARTDATETIME": _dt(year_start),
        "ENDDATETIME":   f"{year_end}1231235959",
    }

    for attempt in range(1, GDELT_MAX_RETRIES + 1):
        try:
            logger.debug(
                "GDELT request country=%s theme=%s years=%d-%d (attempt %d)",
                country_gdelt, theme_query, year_start, year_end, attempt,
            )
            resp = cf.get(
                GDELT_DOC_API,
                params=params,
                headers=GDELT_HEADERS,
                impersonate="chrome124",
                timeout=90,
            )

            # Hard rate-limit — back off and retry.
            if resp.status_code == 429:
                wait = GDELT_RETRY_BACKOFF * attempt
                logger.warning(
                    "GDELT 429 country=%s theme=%s – backing off %.0fs (attempt %d/%d)",
                    country_gdelt, theme_query, wait, attempt, GDELT_MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()

            # Empty body = soft rate-limit or no data for this query.
            if not resp.text.strip():
                wait = GDELT_RETRY_BACKOFF * attempt
                logger.warning(
                    "GDELT empty body country=%s theme=%s – backing off %.0fs (attempt %d/%d)",
                    country_gdelt, theme_query, wait, attempt, GDELT_MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            data = resp.json()
            timeline = data.get("timeline", [])
            if not timeline:
                logger.info("GDELT no data country=%s theme=%s", country_gdelt, theme_query)
                return []

            points = timeline[0].get("data", [])
            logger.info(
                "GDELT OK country=%s theme=%s – %d data points",
                country_gdelt, theme_query, len(points),
            )
            return points

        except ValueError as exc:
            # JSON decode failure (malformed / HTML error page).
            wait = GDELT_RETRY_BACKOFF * attempt
            logger.warning(
                "GDELT JSON error country=%s theme=%s: %s – backing off %.0fs (attempt %d/%d)",
                country_gdelt, theme_query, exc, wait, attempt, GDELT_MAX_RETRIES,
            )
            time.sleep(wait)

        except requests.RequestException as exc:
            wait = GDELT_RETRY_BACKOFF * attempt
            logger.warning(
                "GDELT network error country=%s theme=%s: %s – backing off %.0fs (attempt %d/%d)",
                country_gdelt, theme_query, exc, wait, attempt, GDELT_MAX_RETRIES,
            )
            time.sleep(wait)

    logger.error(
        "GDELT giving up country=%s theme=%s after %d attempts",
        country_gdelt, theme_query, GDELT_MAX_RETRIES,
    )
    return []


def _parse_year_month(date_str: str) -> Optional[tuple]:
    """
    Parse GDELT date string 'YYYYMMDDHHMMSS' → (year, month).
    Returns None if the string is too short.
    """
    if len(date_str) >= 6:
        return int(date_str[:4]), int(date_str[4:6])
    return None


def ingest_gdelt(db: Session, year_start: int = 2015, year_end: int = 2023) -> int:
    from models import GdeltEvent, EventType, IngestionLog

    log = IngestionLog(source="gdelt", status="running")
    db.add(log)
    db.commit()

    event_types = {et.theme_code: et for et in db.query(EventType).all()}
    total = 0
    total_requests = len(GDELT_COUNTRY_MAP) * len(THEME_QUERY_MAP)
    done_requests = 0

    try:
        for code3, code_gdelt in GDELT_COUNTRY_MAP.items():
            for theme_code, theme_query in THEME_QUERY_MAP.items():
                et = event_types.get(theme_code)
                if not et:
                    continue

                done_requests += 1
                logger.info(
                    "GDELT ingesting %s/%s (%d/%d)",
                    code3, theme_code, done_requests, total_requests,
                )

                # One request for the full year range.
                points = fetch_timeline_range(code_gdelt, theme_query, year_start, year_end)

                # Aggregate weekly data points → monthly counts per year.
                monthly: dict = {}   # (year, month) → cumulative count
                for point in points:
                    parsed = _parse_year_month(point.get("date", ""))
                    if not parsed:
                        continue
                    yr, mo = parsed
                    if year_start <= yr <= year_end:
                        key = (yr, mo)
                        monthly[key] = monthly.get(key, 0) + int(point.get("value", 0))

                # Upsert into DB.
                for (yr, mo), count in monthly.items():
                    existing = db.query(GdeltEvent).filter_by(
                        country_code=code3,
                        event_type_id=et.id,
                        year=yr,
                        month=mo,
                    ).first()
                    if existing:
                        existing.article_count = count
                    else:
                        db.add(GdeltEvent(
                            country_code=code3,
                            event_type_id=et.id,
                            year=yr,
                            month=mo,
                            article_count=count,
                        ))
                    total += 1

                # Commit after each (country, theme) to preserve partial progress.
                db.commit()

                # Respect GDELT rate limit between requests.
                if done_requests < total_requests:
                    time.sleep(GDELT_REQUEST_DELAY)

        log.status = "success"
        log.records_fetched = total

    except Exception as exc:
        db.rollback()
        log.status = "error"
        log.error_message = str(exc)
        logger.exception("GDELT ingestion failed")

    finally:
        log.finished_at = datetime.utcnow()
        db.commit()

    logger.info("GDELT ingestion complete: %d records", total)
    return total
