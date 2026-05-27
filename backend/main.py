"""
GDP Events Analysis – Backend API
FastAPI application with Swagger documentation at /docs
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import engine, get_db
from routers import gdp, events, analysis
from schemas import HealthOut

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backend")

app = FastAPI(
    title="GDP & Events Analysis API",
    description=(
        "Analyzes the relationship between countries' GDP changes (World Bank API) "
        "and the volume of global events (GDELT Project API)."
    ),
    version="1.0.0",
    contact={"name": "Mini-projekt PW MiNI"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(gdp.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")


@app.get("/health", response_model=HealthOut, tags=["System"])
def health():
    """Health check endpoint."""
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        logger.error("DB health check failed: %s", e)
        db_status = "error"
    return HealthOut(status="ok", db=db_status, version="1.0.0")


@app.get("/", tags=["System"])
def root():
    return {"message": "GDP Events Analysis API", "docs": "/docs", "health": "/health"}
