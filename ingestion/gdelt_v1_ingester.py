"""
GDELT v1 GKG (Global Knowledge Graph) ingester.
Fills the historical gap for years where the v2 Doc API has no data.

Coverage: 2013-04-01 → 2016-12-31
  (GKG v1 started April 2013; v2 Doc API takes over from 2017)

Data source: daily GKG files
  http://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip

GKG v1 tab-separated columns (0-indexed):
  0  DATE         YYYYMMDD
  1  NUMARTS      raw article count for this cluster
  2  COUNTS       named counts (not used here)
  3  THEMES       semicolon-separated theme codes  e.g. "PROTEST;ELECTIONS"
  4  LOCATIONS    semicolon-separated location entries
  ...

LOCATIONS entry format (hash-separated):
  Type#FullName#CountryCode#ADM1Code#LocationName#Lat#Long#FeatureID
  CountryCode is FIPS 10-4  (e.g. PL, GM, US)

Normalization note
──────────────────
v1 NUMARTS  = raw integer article count  (e.g. 45, 120)
v2 timelinevol = volume units comparable to article counts

For Pearson correlation the scale is irrelevant (r is scale-invariant).
Both v1 and v2 store their values in the same integer article_count column.
"""
import csv
import io
import logging
import time
import zipfile
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

GKG_V1_BASE       = "http://data.gdeltproject.org/gkg"
GKG_V1_START      = date(2013, 4, 1)   # first GKG file ever published
GKG_REQUEST_DELAY = 0.5                # seconds between downloads (polite)
GKG_TIMEOUT       = 60                 # seconds per HTTP request

# Column indices in the tab-separated GKG v1 file
_COL_NUMARTS   = 1
_COL_THEMES    = 3
_COL_LOCATIONS = 4

# FIPS 10-4 codes used in GKG LOCATIONS → our ISO-3 codes
_FIPS_TO_ISO3: dict[str, str] = {
    "PL": "POL", "GM": "DEU", "US": "USA", "FR": "FRA",
    "BR": "BRA", "IN": "IND", "CH": "CHN", "JA": "JPN",
    "UK": "GBR", "IT": "ITA",
}
_TARGET_FIPS = set(_FIPS_TO_ISO3.keys())

# Maps our theme_code → set of GKG v1 theme tokens (substring match)
# GKG v1 and v2 share the same GDELT theme taxonomy, so codes are identical.
GKG_THEME_TOKENS: dict[str, set[str]] = {
    "PROTEST":  {"PROTEST"},
    "MILITARY": {"KILL", "ARMED_CONFLICT"},
    "ELECTION": {"ELECTION", "ELECTIONS"},
    "ECONOMY":  {"ECON_BANKRUPTCY", "ECON_RECESSION"},
    "DISASTER": {"NATURAL_DISASTER", "ENV_DISASTER"},
    "CRIME":    {"CRIME_MURDER", "CRIMEVIOLENCE"},
}

# Pre-compute reverse lookup: token → theme_code (for fast matching)
_TOKEN_TO_THEME: dict[str, str] = {
    token: theme
    for theme, tokens in GKG_THEME_TOKENS.items()
    for token in tokens
}


# ── parsing helpers ───────────────────────────────────────────────────────────

def _extract_countries(locations_str: str) -> set[str]:
    """
    Parse LOCATIONS field, return set of FIPS codes that are in our target list.
    Each location entry: Type#FullName#CountryCode#ADM1Code#...
    """
    if not locations_str:
        return set()
    result: set[str] = set()
    for entry in locations_str.split(";"):
        parts = entry.split("#")
        if len(parts) >= 3:
            fips = parts[2].strip()
            if fips in _TARGET_FIPS:
                result.add(fips)
    return result


def _extract_themes(themes_str: str) -> set[str]:
    """
    Parse THEMES field, return set of our theme_codes that are present.
    Themes in GKG: "PROTEST;ELECTIONS;ECON_BANKRUPTCY;TAX_FNCACT"
    """
    if not themes_str:
        return set()
    matched: set[str] = set()
    for token in themes_str.split(";"):
        token = token.strip()
        theme = _TOKEN_TO_THEME.get(token)
        if theme:
            matched.add(theme)
    return matched


# ── single-day fetch ──────────────────────────────────────────────────────────

def fetch_gkg_day(day: date) -> Optional[dict[tuple, int]]:
    """
    Download one GKG v1 daily file and count articles per (FIPS, theme_code).

    Returns  {(fips_code, theme_code): article_count}  or
             {}  if the file doesn't exist (e.g. no data for that day)
             None on network/parse error (caller should log and continue)
    """
    url = f"{GKG_V1_BASE}/{day.strftime('%Y%m%d')}.gkg.csv.zip"
    try:
        resp = requests.get(url, timeout=GKG_TIMEOUT)
        if resp.status_code == 404:
            logger.debug("GKG v1: no file for %s", day)
            return {}
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("GKG v1 download error %s: %s", day, exc)
        return None

    counts: dict[tuple, int] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            inner_name = zf.namelist()[0]
            with zf.open(inner_name) as raw:
                reader = csv.reader(
                    io.TextIOWrapper(raw, encoding="utf-8", errors="replace"),
                    delimiter="\t",
                )
                for row in reader:
                    if len(row) <= _COL_LOCATIONS:
                        continue
                    try:
                        numarts = int(row[_COL_NUMARTS])
                    except ValueError:
                        continue
                    if numarts == 0:
                        continue

                    countries = _extract_countries(row[_COL_LOCATIONS])
                    if not countries:
                        continue

                    themes = _extract_themes(row[_COL_THEMES])
                    if not themes:
                        continue

                    for fips in countries:
                        for theme in themes:
                            key = (fips, theme)
                            counts[key] = counts.get(key, 0) + numarts

    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
        logger.warning("GKG v1 parse error %s: %s", day, exc)
        return None

    return counts


# ── main ingestion ────────────────────────────────────────────────────────────

def ingest_gdelt_v1(
    db: Session,
    year_start: int = 2013,
    year_end:   int = 2016,
) -> int:
    """
    Ingest GDELT v1 GKG data for the given year range.
    Automatically clamps to GKG availability (2013-04-01 onwards).
    Safe to re-run — uses ON CONFLICT DO UPDATE.
    """
    from models import GdeltEvent, EventType, IngestionLog
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    start_date = max(date(year_start, 1, 1), GKG_V1_START)
    end_date   = date(year_end, 12, 31)

    if start_date > end_date:
        logger.info(
            "GKG v1: nothing to ingest (requested %d-%d, GKG starts %s)",
            year_start, year_end, GKG_V1_START,
        )
        return 0

    logger.info(
        "GKG v1 ingestion starting: %s → %s (~%d days)",
        start_date, end_date, (end_date - start_date).days + 1,
    )

    log = IngestionLog(source="gdelt_v1_gkg", status="running")
    db.add(log)
    db.commit()

    event_types: dict[str, int] = {
        et.theme_code: et.id for et in db.query(EventType).all()
    }

    total      = 0
    days_total = (end_date - start_date).days + 1
    days_done  = 0

    # Accumulate one month at a time before committing
    monthly: dict[tuple, int] = {}
    current_month = (start_date.year, start_date.month)

    try:
        current = start_date
        while current <= end_date:
            days_done += 1
            this_month = (current.year, current.month)

            # Flush previous month when the month rolls over
            if this_month != current_month:
                yr, mo = current_month
                n = _flush_month(db, pg_insert, monthly, event_types, yr, mo)
                total += n
                logger.info(
                    "GKG v1: %d-%02d committed (%d records). Progress: %d/%d days",
                    yr, mo, n, days_done, days_total,
                )
                monthly = {}
                current_month = this_month

            day_counts = fetch_gkg_day(current)

            if day_counts is not None:
                yr, mo = current.year, current.month
                for (fips, theme_code), count in day_counts.items():
                    iso3 = _FIPS_TO_ISO3.get(fips)
                    if not iso3:
                        continue
                    key = (iso3, theme_code, yr, mo)
                    monthly[key] = monthly.get(key, 0) + count

            current += timedelta(days=1)
            time.sleep(GKG_REQUEST_DELAY)

        # Flush the final month
        if monthly:
            yr, mo = current_month
            n = _flush_month(db, pg_insert, monthly, event_types, yr, mo)
            total += n
            logger.info("GKG v1: %d-%02d committed (%d records) — final month", yr, mo, n)

        log.status          = "success"
        log.records_fetched = total

    except Exception as exc:
        db.rollback()
        log.status        = "error"
        log.error_message = str(exc)
        logger.exception("GKG v1 ingestion failed")

    finally:
        log.finished_at = datetime.utcnow()
        db.commit()

    logger.info("GKG v1 ingestion complete: %d records (%s → %s)", total, start_date, end_date)
    return total


def _flush_month(
    db, pg_insert, monthly: dict, event_types: dict, yr: int, mo: int
) -> int:
    """Upsert all accumulated monthly counts and commit."""
    from models import GdeltEvent
    n = 0
    for (iso3, theme_code, y, m), count in monthly.items():
        et_id = event_types.get(theme_code)
        if not et_id:
            continue
        stmt = pg_insert(GdeltEvent.__table__).values(
            country_code  = iso3,
            event_type_id = et_id,
            year  = y,
            month = m,
            article_count = count,
        ).on_conflict_do_update(
            index_elements=["country_code", "event_type_id", "year", "month"],
            set_={"article_count": count},
        )
        db.execute(stmt)
        n += 1
    db.commit()
    return n
