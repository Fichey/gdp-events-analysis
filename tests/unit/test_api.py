"""Integration tests for the FastAPI backend."""
import pytest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

# Patch create_engine before any backend module is imported so that
# database.py never attempts a real TCP connection during the test run.
with patch("sqlalchemy.create_engine", return_value=MagicMock()):
    from main import app
    from database import get_db

from fastapi.testclient import TestClient

client = TestClient(app)


def _db_override(mock_db: MagicMock):
    """Wrap a mock DB session as a FastAPI dependency."""
    def _inner():
        yield mock_db
    return _inner


@pytest.fixture(autouse=True)
def clear_overrides():
    """Remove any dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


class TestHealthEndpoint:
    def test_health_returns_200(self):
        db = MagicMock()
        db.execute.return_value = MagicMock()
        app.dependency_overrides[get_db] = _db_override(db)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestRootEndpoint:
    def test_root_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "docs" in resp.json()


class TestGdpEndpoints:
    def test_list_countries_ok(self):
        mock_country = MagicMock()
        mock_country.code = "POL"
        mock_country.name = "Poland"
        db = MagicMock()
        db.query.return_value.order_by.return_value.all.return_value = [mock_country]
        app.dependency_overrides[get_db] = _db_override(db)
        resp = client.get("/api/v1/gdp/countries")
        assert resp.status_code == 200

    def test_get_gdp_country_not_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        app.dependency_overrides[get_db] = _db_override(db)
        resp = client.get("/api/v1/gdp/ZZZ")
        assert resp.status_code == 404


class TestEventsEndpoints:
    def test_list_event_types_ok(self):
        db = MagicMock()
        db.query.return_value.all.return_value = []
        app.dependency_overrides[get_db] = _db_override(db)
        resp = client.get("/api/v1/events/types")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
