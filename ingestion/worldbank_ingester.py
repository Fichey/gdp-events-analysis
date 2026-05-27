"""
World Bank Open Data API ingester.
Fetches GDP data (indicator NY.GDP.MKTP.CD) for configured countries.
No API key required.
"""
import logging
import time
from typing import Optional

import requests
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

WORLDBANK_BASE = "https://api.worldbank.org/v2"
GDP_INDICATOR = "NY.GDP.MKTP.CD"
GROWTH_INDICATOR = "NY.GDP.MKTP.KD.ZG"

# WB uses ISO alpha-2/alpha-3 codes - mapping from our 3-letter codes
WB_COUNTRY_MAP = {
    "POL": "PL", "DEU": "DE", "USA": "US", "FRA": "FR",
    "BRA": "BR", "IND": "IN", "CHN": "CN", "JPN": "JP",
    "GBR": "GB", "ITA": "IT",
}


def fetch_indicator(country_alpha2: str, indicator: str, year_start: int, year_end: int) -> list[dict]:
    url = f"{WORLDBANK_BASE}/country/{country_alpha2}/indicator/{indicator}"
    params = {
        "format": "json",
        "date": f"{year_start}:{year_end}",
        "per_page": 100,
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2 or not data[1]:
            return []
        return data[1]
    except requests.RequestException as e:
        logger.error("WorldBank request failed for %s/%s: %s", country_alpha2, indicator, e)
        return []


def ingest_gdp(db: Session, year_start: int = 2010, year_end: int = 2023) -> int:
    from ingestion.models import GdpData, IngestionLog

    log = IngestionLog(source="worldbank", status="running")
    db.add(log)
    db.commit()

    total = 0
    try:
        for code3, code2 in WB_COUNTRY_MAP.items():
            gdp_records = fetch_indicator(code2, GDP_INDICATOR, year_start, year_end)
            growth_records = fetch_indicator(code2, GROWTH_INDICATOR, year_start, year_end)

            growth_by_year = {
                r["date"]: r["value"]
                for r in growth_records
                if r.get("value") is not None
            }

            for record in gdp_records:
                if record.get("value") is None:
                    continue
                year = int(record["date"])
                gdp_usd = record["value"]
                growth = growth_by_year.get(str(year))

                existing = db.query(GdpData).filter_by(country_code=code3, year=year).first()
                if existing:
                    existing.gdp_usd = gdp_usd
                    existing.gdp_growth_rate = growth
                else:
                    db.add(GdpData(country_code=code3, year=year, gdp_usd=gdp_usd, gdp_growth_rate=growth))
                total += 1

            time.sleep(0.5)  # respect rate limits

        db.commit()
        log.status = "success"
        log.records_fetched = total
    except Exception as e:
        db.rollback()
        log.status = "error"
        log.error_message = str(e)
        logger.exception("GDP ingestion failed")
    finally:
        from datetime import datetime
        log.finished_at = datetime.utcnow()
        db.commit()

    logger.info("WorldBank ingestion complete: %d records", total)
    return total
