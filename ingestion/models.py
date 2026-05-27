from datetime import datetime
from sqlalchemy import Column, Integer, String, Numeric, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Country(Base):
    __tablename__ = "countries"
    id = Column(Integer, primary_key=True)
    code = Column(String(3), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class GdpData(Base):
    __tablename__ = "gdp_data"
    id = Column(Integer, primary_key=True)
    country_code = Column(String(3), ForeignKey("countries.code"), nullable=False)
    year = Column(Integer, nullable=False)
    gdp_usd = Column(Numeric(25, 2))
    gdp_growth_rate = Column(Numeric(10, 4))
    ingested_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("country_code", "year"),)


class EventType(Base):
    __tablename__ = "event_types"
    id = Column(Integer, primary_key=True)
    theme_code = Column(String(50), unique=True, nullable=False)
    theme_name = Column(String(100), nullable=False)
    description = Column(Text)


class GdeltEvent(Base):
    __tablename__ = "gdelt_events"
    id = Column(Integer, primary_key=True)
    country_code = Column(String(3), ForeignKey("countries.code"), nullable=False)
    event_type_id = Column(Integer, ForeignKey("event_types.id"))
    year = Column(Integer, nullable=False)
    month = Column(Integer)
    article_count = Column(Integer, default=0)
    ingested_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("country_code", "event_type_id", "year", "month"),)


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id = Column(Integer, primary_key=True)
    country_code = Column(String(3), ForeignKey("countries.code"))
    event_type_id = Column(Integer, ForeignKey("event_types.id"))
    year_start = Column(Integer)
    year_end = Column(Integer)
    correlation_coefficient = Column(Numeric(10, 6))
    sample_size = Column(Integer)
    calculated_at = Column(DateTime, default=datetime.utcnow)


class IngestionLog(Base):
    __tablename__ = "ingestion_log"
    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    records_fetched = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
