"""
Ingestion scheduler. Runs once on start, then daily.
Can also be invoked directly via CLI:
  python scheduler.py --source worldbank
  python scheduler.py --source gdelt
  python scheduler.py --source all

GDELT ingestion strategy (hybrid v1 + v2):
  2013-2016 → GDELT v1 GKG daily files  (gdelt_v1_ingester)
  2017+     → GDELT v2 Doc API           (gdelt_ingester)

  v1 GKG coverage starts 2013-04-01. Data for 2010-2012 is not available
  from any GDELT REST API without bulk BigQuery access.
"""
import argparse
import logging
import os
import time

from database import SessionLocal
from worldbank_ingester import ingest_gdp
from gdelt_ingester import ingest_gdelt
from gdelt_v1_ingester import ingest_gdelt_v1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("scheduler")

YEAR_START         = int(os.getenv("INGEST_YEAR_START",    "2010"))
YEAR_END           = int(os.getenv("INGEST_YEAR_END",      "2025"))
RUN_INTERVAL_HOURS = int(os.getenv("INGEST_INTERVAL_HOURS", "24"))

# Split point between the two GDELT APIs
_V2_START = 2017


def run_ingestion(source: str) -> None:
    db = SessionLocal()
    try:
        if source in ("worldbank", "all"):
            logger.info("Starting WorldBank ingestion (years %d-%d)", YEAR_START, YEAR_END)
            n = ingest_gdp(db, YEAR_START, YEAR_END)
            logger.info("WorldBank: %d records stored", n)

        if source in ("gdelt", "all"):
            # ── v1 GKG: 2013-04-01 up to end of 2016 (or YEAR_END if earlier) ──
            v1_end = min(YEAR_END, _V2_START - 1)
            if YEAR_START <= v1_end:
                logger.info(
                    "Starting GDELT v1 GKG ingestion (years %d-%d)", YEAR_START, v1_end
                )
                n = ingest_gdelt_v1(db, YEAR_START, v1_end)
                logger.info("GDELT v1 GKG: %d records stored", n)

            # ── v2 Doc API: 2017 up to YEAR_END ──────────────────────────────
            v2_start = max(YEAR_START, _V2_START)
            if v2_start <= YEAR_END:
                logger.info(
                    "Starting GDELT v2 Doc API ingestion (years %d-%d)", v2_start, YEAR_END
                )
                n = ingest_gdelt(db, v2_start, YEAR_END)
                logger.info("GDELT v2: %d records stored", n)

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
