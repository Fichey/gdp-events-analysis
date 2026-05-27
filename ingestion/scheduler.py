"""
Ingestion scheduler. Runs once on start, then daily.
Can also be invoked directly via CLI:
  python scheduler.py --source worldbank
  python scheduler.py --source gdelt
  python scheduler.py --source all
"""
import argparse
import logging
import os
import time

from database import SessionLocal
from worldbank_ingester import ingest_gdp
from gdelt_ingester import ingest_gdelt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("scheduler")

YEAR_START = int(os.getenv("INGEST_YEAR_START", "2015"))
YEAR_END = int(os.getenv("INGEST_YEAR_END", "2023"))
RUN_INTERVAL_HOURS = int(os.getenv("INGEST_INTERVAL_HOURS", "24"))


def run_ingestion(source: str) -> None:
    db = SessionLocal()
    try:
        if source in ("worldbank", "all"):
            logger.info("Starting WorldBank ingestion (years %d-%d)", YEAR_START, YEAR_END)
            n = ingest_gdp(db, YEAR_START, YEAR_END)
            logger.info("WorldBank: %d records stored", n)

        if source in ("gdelt", "all"):
            logger.info("Starting GDELT ingestion (years %d-%d)", YEAR_START, YEAR_END)
            n = ingest_gdelt(db, YEAR_START, YEAR_END)
            logger.info("GDELT: %d records stored", n)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["worldbank", "gdelt", "all"], default="all")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    run_ingestion(args.source)

    if not args.once:
        while True:
            logger.info("Next ingestion in %d hours", RUN_INTERVAL_HOURS)
            time.sleep(RUN_INTERVAL_HOURS * 3600)
            run_ingestion(args.source)


if __name__ == "__main__":
    main()
