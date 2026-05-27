"""Integration tests for the FastAPI backend."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))


def make_client():
    with patch("database.engine"):
        with patch("database.SessionLocal"):
            from main import app
            return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self):
        client = make_client()
        with patch("main.get_db") as mock_db:
            db = MagicMock()
            db.execute.return_value = MagicMock()
            mock_db.return_value = iter([db])
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestRootEndpoint:
    def test_root_returns_200(self):
        client = make_client()
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "docs" in body


class TestGdpEndpoints:
    def test_list_countries_ok(self):
        client = make_client()
        mock_country = MagicMock()
        mock_country.code = "POL"
        mock_country.name = "Poland"
        with patch("routers.gdp.get_db") as mock_db:
            db = MagicMock()
            db.query.return_value.order_by.return_value.all.return_value = [mock_country]
            mock_db.return_value = iter([db])
            resp = client.get("/api/v1/gdp/countries")
        assert resp.status_code == 200

    def test_get_gdp_country_not_found(self):
        client = make_client()
        with patch("routers.gdp.get_db") as mock_db:
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = None
            mock_db.return_value = iter([db])
            resp = client.get("/api/v1/gdp/ZZZ")
        assert resp.status_code == 404


class TestEventsEndpoints:
    def test_list_event_types_ok(self):
        client = make_client()
        with patch("routers.events.get_db") as mock_db:
            db = MagicMock()
            db.query.return_value.all.return_value = []
            mock_db.return_value = iter([db])
            resp = client.get("/api/v1/events/types")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
