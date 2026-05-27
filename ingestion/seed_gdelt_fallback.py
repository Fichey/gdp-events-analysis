"""
Fallback seed script – populates gdelt_events with realistic synthetic data
when the GDELT API is unavailable (rate-limited / blocked).

Uses PostgreSQL ON CONFLICT DO UPDATE so re-running never creates duplicates.
Year range: 2010–2025  (16 years × 10 countries × 6 themes × 12 months = 11 520 rows)

Run inside the ingestion container:
  docker compose run --rm ingestion python seed_gdelt_fallback.py
"""
import random
import logging
from datetime import datetime
from database import SessionLocal
from models import GdeltEvent, EventType, IngestionLog
from sqlalchemy.dialects.postgresql import insert as pg_insert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed")

random.seed(42)

YEAR_START = 2010
YEAR_END   = 2025

COUNTRIES = ["POL", "DEU", "USA", "FRA", "BRA", "IND", "CHN", "JPN", "GBR", "ITA"]

# Base monthly article counts per theme per country
BASE = {
    "PROTEST":  {"POL":40,"DEU":55,"USA":90,"FRA":70,"BRA":60,"IND":50,"CHN":20,"JPN":30,"GBR":65,"ITA":50},
    "MILITARY": {"POL":25,"DEU":30,"USA":80,"FRA":40,"BRA":35,"IND":55,"CHN":45,"JPN":20,"GBR":35,"ITA":25},
    "ELECTION": {"POL":20,"DEU":20,"USA":30,"FRA":20,"BRA":20,"IND":25,"CHN":10,"JPN":15,"GBR":20,"ITA":20},
    "ECONOMY":  {"POL":30,"DEU":50,"USA":75,"FRA":45,"BRA":40,"IND":35,"CHN":55,"JPN":50,"GBR":55,"ITA":40},
    "DISASTER": {"POL":15,"DEU":20,"USA":40,"FRA":18,"BRA":35,"IND":45,"CHN":40,"JPN":50,"GBR":18,"ITA":22},
    "CRIME":    {"POL":20,"DEU":25,"USA":60,"FRA":30,"BRA":55,"IND":40,"CHN":15,"JPN":10,"GBR":35,"ITA":30},
}

# Year-level multipliers capturing macro trends
YEAR_MULT = {
    "PROTEST":  {2010:0.8,2011:0.9,2012:1.0,2013:1.0,2014:1.1,2015:1.0,2016:1.1,2017:1.2,
                 2018:1.1,2019:1.3,2020:2.1,2021:1.9,2022:1.5,2023:1.2,2024:1.1,2025:1.0},
    "MILITARY": {2010:0.9,2011:1.0,2012:1.1,2013:1.2,2014:1.3,2015:1.2,2016:1.1,2017:1.0,
                 2018:1.0,2019:1.1,2020:1.2,2021:1.3,2022:2.5,2023:2.2,2024:2.0,2025:1.9},
    "ELECTION": {2010:1.2,2011:1.0,2012:1.8,2013:1.0,2014:1.4,2015:1.5,2016:2.0,2017:1.5,
                 2018:1.2,2019:1.6,2020:2.2,2021:1.8,2022:1.4,2023:1.3,2024:1.6,2025:1.2},
    "ECONOMY":  {2010:1.5,2011:1.3,2012:1.2,2013:1.1,2014:1.1,2015:1.0,2016:1.0,2017:1.1,
                 2018:1.2,2019:1.1,2020:2.5,2021:1.8,2022:1.6,2023:1.3,2024:1.2,2025:1.1},
    "DISASTER": {2010:1.4,2011:1.5,2012:1.1,2013:1.2,2014:1.1,2015:1.1,2016:1.2,2017:1.3,
                 2018:1.1,2019:1.2,2020:1.5,2021:1.3,2022:1.2,2023:1.4,2024:1.3,2025:1.2},
    "CRIME":    {2010:1.0,2011:1.0,2012:1.0,2013:1.0,2014:1.1,2015:1.0,2016:1.0,2017:1.0,
                 2018:1.1,2019:1.1,2020:1.6,2021:1.4,2022:1.2,2023:1.1,2024:1.0,2025:1.0},
}

# Country+theme specific monthly spikes (year, month) → extra multiplier
SPIKES = {
    ("POL","PROTEST"): {(2020,10):5.0,(2020,11):4.5,(2021,1):3.0,(2023,6):2.0},
    ("POL","ELECTION"): {(2015,10):5.0,(2019,10):5.5,(2023,10):6.0},
    ("POL","MILITARY"): {(2022,2):4.0,(2022,3):3.5,(2022,4):3.0,(2024,3):2.5},
    ("USA","PROTEST"):  {(2020,6):6.0,(2020,7):4.0,(2021,1):3.5,(2024,6):2.5},
    ("USA","ELECTION"): {(2012,11):5.0,(2016,11):6.0,(2020,11):7.0,(2024,11):6.5},
    ("USA","ECONOMY"):  {(2020,3):4.0,(2020,4):4.5,(2020,5):3.5},
    ("DEU","ELECTION"): {(2013,9):5.5,(2017,9):6.0,(2021,9):6.5},
    ("DEU","ECONOMY"):  {(2020,4):3.5,(2020,5):3.0},
    ("FRA","PROTEST"):  {(2018,12):4.0,(2019,1):3.5,(2019,3):3.0,(2023,3):3.5},
    ("FRA","ELECTION"): {(2017,5):5.5,(2022,4):5.0},
    ("GBR","ELECTION"): {(2010,5):4.5,(2015,5):5.0,(2017,6):4.5,(2019,12):5.0},
    ("GBR","ECONOMY"):  {(2016,7):3.0,(2022,10):3.5},   # Brexit/Truss crisis
    ("BRA","ECONOMY"):  {(2015,1):3.0,(2016,1):3.5,(2020,4):4.0},
    ("IND","ECONOMY"):  {(2016,11):3.5,(2020,4):3.5},   # demonetisation / COVID
    ("JPN","DISASTER"): {(2011,3):8.0,(2011,4):5.0,(2011,5):3.0},  # Fukushima
    ("CHN","ECONOMY"):  {(2015,8):3.5,(2018,10):3.0,(2020,2):4.0},
    ("ITA","ECONOMY"):  {(2011,11):4.0,(2012,6):3.5,(2020,4):4.5},
    ("ITA","ELECTION"): {(2018,3):5.0,(2022,9):5.5},
}


def generate_count(country: str, theme: str, year: int, month: int) -> int:
    base  = BASE[theme][country]
    ym    = YEAR_MULT[theme].get(year, 1.0)
    spike = SPIKES.get((country, theme), {}).get((year, month), 1.0)
    noise = random.uniform(0.75, 1.25)
    return max(1, int(base * ym * spike * noise))


def seed():
    db = SessionLocal()
    try:
        event_types = {et.theme_code: et for et in db.query(EventType).all()}
        if not event_types:
            logger.error("No event types in DB – run db migrations first")
            return

        log = IngestionLog(source="gdelt_seed", status="running")
        db.add(log)
        db.commit()

        total = 0
        for country in COUNTRIES:
            for theme, et in event_types.items():
                if theme not in BASE:
                    continue
                for year in range(YEAR_START, YEAR_END + 1):
                    for month in range(1, 13):
                        count = generate_count(country, theme, year, month)
                        stmt = pg_insert(GdeltEvent.__table__).values(
                            country_code=country,
                            event_type_id=et.id,
                            year=year,
                            month=month,
                            article_count=count,
                        ).on_conflict_do_update(
                            index_elements=["country_code", "event_type_id", "year", "month"],
                            set_={"article_count": count},
                        )
                        db.execute(stmt)
                        total += 1

            db.commit()
            logger.info("Seeded country %s (%d records so far)", country, total)

        log.status = "success"
        log.records_fetched = total
        log.finished_at = datetime.utcnow()
        db.commit()
        logger.info("Seed complete: %d records (%d years × %d countries × 6 themes × 12 months)",
                    total, YEAR_END - YEAR_START + 1, len(COUNTRIES))

    except Exception as e:
        db.rollback()
        logger.exception("Seed failed: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
