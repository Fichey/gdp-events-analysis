"""Unit tests for World Bank ingester."""
import pytest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../ingestion'))

from worldbank_ingester import fetch_indicator, WB_COUNTRY_MAP


class TestFetchIndicator:
    def test_returns_empty_on_http_error(self):
        import requests as _requests
        with patch("worldbank_ingester.requests.get") as mock_get:
            mock_get.side_effect = _requests.RequestException("500")
            result = fetch_indicator("PL", "NY.GDP.MKTP.CD", 2020, 2022)
        assert result == []

    def test_returns_empty_when_no_data_field(self):
        with patch("worldbank_ingester.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = [{"total": 0}, None]
            mock_get.return_value = mock_resp
            result = fetch_indicator("PL", "NY.GDP.MKTP.CD", 2020, 2022)
        assert result == []

    def test_parses_valid_response(self):
        payload = [
            {"pages": 1},
            [
                {"date": "2020", "value": 596000000000.0, "country": {"id": "PL"}},
                {"date": "2021", "value": 679000000000.0, "country": {"id": "PL"}},
            ],
        ]
        with patch("worldbank_ingester.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = payload
            mock_get.return_value = mock_resp
            result = fetch_indicator("PL", "NY.GDP.MKTP.CD", 2020, 2021)
        assert len(result) == 2
        assert result[0]["date"] == "2020"

    def test_country_map_contains_all_expected(self):
        expected = {"POL", "DEU", "USA", "FRA", "BRA", "IND", "CHN", "JPN", "GBR", "ITA"}
        assert expected.issubset(set(WB_COUNTRY_MAP.keys()))

    def test_url_construction_uses_correct_indicator(self):
        with patch("worldbank_ingester.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = [{"pages": 0}, []]
            mock_get.return_value = mock_resp
            fetch_indicator("US", "NY.GDP.MKTP.CD", 2020, 2021)
        call_url = mock_get.call_args[0][0]
        assert "NY.GDP.MKTP.CD" in call_url
        assert "US" in call_url


