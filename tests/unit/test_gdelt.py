"""Unit tests for GDELT ingester."""
import pytest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../ingestion'))

from gdelt_ingester import fetch_timeline_volume, _parse_month, GDELT_COUNTRY_MAP, THEME_QUERY_MAP


class TestParseMonth:
    def test_parses_valid_date(self):
        assert _parse_month("20200315120000") == 3

    def test_returns_none_for_short_string(self):
        assert _parse_month("2020") is None

    def test_parses_month_12(self):
        assert _parse_month("20201201000000") == 12

    def test_parses_month_01(self):
        assert _parse_month("20200101000000") == 1


class TestFetchTimelineVolume:
    def test_returns_empty_on_http_error(self):
        with patch("gdelt_ingester.requests.get") as mock_get:
            mock_get.return_value.raise_for_status.side_effect = Exception("timeout")
            result = fetch_timeline_volume("US", "PROTEST", 2020)
        assert result == []

    def test_returns_empty_when_no_timeline_key(self):
        with patch("gdelt_ingester.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = {}
            mock_get.return_value = mock_resp
            result = fetch_timeline_volume("US", "PROTEST", 2020)
        assert result == []

    def test_parses_timeline_data(self):
        payload = {
            "timeline": [{
                "data": [
                    {"date": "20200115120000", "value": 150},
                    {"date": "20200215120000", "value": 200},
                ]
            }]
        }
        with patch("gdelt_ingester.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.return_value = None
            mock_resp.json.return_value = payload
            mock_get.return_value = mock_resp
            result = fetch_timeline_volume("US", "PROTEST", 2020)
        assert len(result) == 2
        assert result[0]["value"] == 150

    def test_country_map_has_gdelt_codes(self):
        assert GDELT_COUNTRY_MAP["USA"] == "US"
        assert GDELT_COUNTRY_MAP["DEU"] == "GM"
        assert GDELT_COUNTRY_MAP["GBR"] == "UK"

    def test_theme_query_map_covers_all_types(self):
        expected = {"PROTEST", "MILITARY", "ELECTION", "ECONOMY", "DISASTER", "CRIME"}
        assert expected == set(THEME_QUERY_MAP.keys())
