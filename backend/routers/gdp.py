from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from models import GdpData, Country
from schemas import GdpDataOut, CountryOut

router = APIRouter(prefix="/gdp", tags=["GDP"])


@router.get("/countries", response_model=list[CountryOut])
def list_countries(db: Session = Depends(get_db)):
    """Returns all available countries."""
    return db.query(Country).order_by(Country.name).all()


@router.get("/{country_code}", response_model=list[GdpDataOut])
def get_gdp(
    country_code: str,
    year_start: Optional[int] = Query(None, ge=1990, le=2030),
    year_end: Optional[int] = Query(None, ge=1990, le=2030),
    db: Session = Depends(get_db),
):
    """Returns GDP data for a given country, optionally filtered by year range."""
    country = db.query(Country).filter(Country.code == country_code.upper()).first()
    if not country:
        raise HTTPException(status_code=404, detail="Country not found")

    q = db.query(GdpData).filter(GdpData.country_code == country_code.upper())
    if year_start:
        q = q.filter(GdpData.year >= year_start)
    if year_end:
        q = q.filter(GdpData.year <= year_end)
    return q.order_by(GdpData.year).all()
