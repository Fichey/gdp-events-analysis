from typing import Optional
from pydantic import BaseModel


class CountryOut(BaseModel):
    code: str
    name: str

    class Config:
        from_attributes = True


class GdpDataOut(BaseModel):
    country_code: str
    year: int
    gdp_usd: Optional[float]
    gdp_growth_rate: Optional[float]

    class Config:
        from_attributes = True


class EventTypeOut(BaseModel):
    id: int
    theme_code: str
    theme_name: str
    description: Optional[str]

    class Config:
        from_attributes = True


class GdeltEventOut(BaseModel):
    country_code: str
    year: int
    month: Optional[int]
    article_count: int
    theme_code: Optional[str] = None
    theme_name: Optional[str] = None

    class Config:
        from_attributes = True


class AnalysisResultOut(BaseModel):
    country_code: str
    theme_code: str
    theme_name: str
    year_start: int
    year_end: int
    correlation_coefficient: float
    sample_size: int

    class Config:
        from_attributes = True


class HealthOut(BaseModel):
    status: str
    db: str
    version: str
