"""Unit tests for app.data.sector_tags.

Tests cover:
- get_sector: known tickers, unknown tickers, case normalisation
- enrich_sector_map: static map priority, yfinance fallback, unknown fallback
- get_tickers_by_sector: returns correct tickers for a sector
- is_valid_gics_sector: valid and invalid sector names
- normalise_sector_name: alias resolution
- SECTOR_MAP: structure and content
- GICS_SECTORS: contains all 11 GICS sectors
"""

from __future__ import annotations

import pytest

from app.data.sector_tags import (
    GICS_SECTORS,
    SECTOR_MAP,
    enrich_sector_map,
    get_sector,
    get_tickers_by_sector,
    is_valid_gics_sector,
    normalise_sector_name,
)


# ---------------------------------------------------------------------------
# GICS_SECTORS
# ---------------------------------------------------------------------------

class TestGicsSectors:
    def test_contains_all_11_sectors(self):
        expected = {
            "Communication Services",
            "Consumer Discretionary",
            "Consumer Staples",
            "Energy",
            "Financials",
            "Health Care",
            "Industrials",
            "Information Technology",
            "Materials",
            "Real Estate",
            "Utilities",
        }
        assert expected == set(GICS_SECTORS)

    def test_is_frozenset(self):
        assert isinstance(GICS_SECTORS, frozenset)

    def test_has_exactly_11_sectors(self):
        assert len(GICS_SECTORS) == 11


# ---------------------------------------------------------------------------
# SECTOR_MAP
# ---------------------------------------------------------------------------

class TestSectorMap:
    def test_is_dict(self):
        assert isinstance(SECTOR_MAP, dict)

    def test_all_values_are_valid_gics_sectors(self):
        for ticker, sector in SECTOR_MAP.items():
            assert sector in GICS_SECTORS, (
                f"Ticker {ticker!r} has invalid sector {sector!r}"
            )

    def test_all_keys_are_uppercase(self):
        for ticker in SECTOR_MAP:
            assert ticker == ticker.upper(), f"Ticker {ticker!r} is not uppercase"

    def test_contains_well_known_tickers(self):
        """Spot-check that common tickers are present."""
        assert "AAPL" in SECTOR_MAP
        assert "MSFT" in SECTOR_MAP
        assert "GOOGL" in SECTOR_MAP
        assert "AMZN" in SECTOR_MAP
        assert "TSLA" in SECTOR_MAP
        assert "JPM" in SECTOR_MAP

    def test_aapl_is_information_technology(self):
        assert SECTOR_MAP["AAPL"] == "Information Technology"

    def test_googl_is_communication_services(self):
        assert SECTOR_MAP["GOOGL"] == "Communication Services"

    def test_jpm_is_financials(self):
        assert SECTOR_MAP["JPM"] == "Financials"


# ---------------------------------------------------------------------------
# get_sector
# ---------------------------------------------------------------------------

class TestGetSector:
    def test_known_ticker_returns_correct_sector(self):
        assert get_sector("AAPL") == "Information Technology"
        assert get_sector("MSFT") == "Information Technology"
        assert get_sector("GOOGL") == "Communication Services"

    def test_unknown_ticker_returns_fallback(self):
        result = get_sector("UNKNOWN_TICKER_XYZ")
        assert result == "Unknown"

    def test_custom_fallback(self):
        result = get_sector("UNKNOWN_TICKER_XYZ", fallback="Other")
        assert result == "Other"

    def test_lowercase_ticker_normalised(self):
        """Lowercase ticker should be normalised to uppercase for lookup."""
        result_lower = get_sector("aapl")
        result_upper = get_sector("AAPL")
        assert result_lower == result_upper

    def test_mixed_case_ticker_normalised(self):
        result = get_sector("AaPl")
        assert result == get_sector("AAPL")

    def test_whitespace_stripped(self):
        result = get_sector("  AAPL  ")
        assert result == "Information Technology"

    def test_empty_string_returns_fallback(self):
        result = get_sector("")
        assert result == "Unknown"


# ---------------------------------------------------------------------------
# enrich_sector_map
# ---------------------------------------------------------------------------

class TestEnrichSectorMap:
    def test_known_tickers_get_static_map_sector(self):
        result = enrich_sector_map(
            tickers=["AAPL", "MSFT"],
            yfinance_map={},
        )
        assert result["AAPL"] == "Information Technology"
        assert result["MSFT"] == "Information Technology"

    def test_yfinance_map_used_for_unknown_tickers(self):
        result = enrich_sector_map(
            tickers=["AAPL", "UNKNOWN_XYZ"],
            yfinance_map={"UNKNOWN_XYZ": "Energy"},
        )
        assert result["UNKNOWN_XYZ"] == "Energy"

    def test_yfinance_takes_priority_over_static_map(self):
        """yfinance data takes priority over the static map (most current data)."""
        result = enrich_sector_map(
            tickers=["AAPL"],
            yfinance_map={"AAPL": "Energy"},  # yfinance overrides static map
        )
        assert result["AAPL"] == "Energy"

    def test_unknown_ticker_not_in_yfinance_gets_unknown(self):
        result = enrich_sector_map(
            tickers=["TOTALLY_UNKNOWN_TICKER"],
            yfinance_map={},
        )
        assert result["TOTALLY_UNKNOWN_TICKER"] == "Unknown"

    def test_all_tickers_present_in_result(self):
        tickers = ["AAPL", "MSFT", "GOOGL", "UNKNOWN_XYZ"]
        result = enrich_sector_map(tickers=tickers, yfinance_map={})
        assert set(result.keys()) == set(tickers)

    def test_empty_tickers_returns_empty_dict(self):
        result = enrich_sector_map(tickers=[], yfinance_map={})
        assert result == {}

    def test_result_values_are_strings(self):
        result = enrich_sector_map(
            tickers=["AAPL", "MSFT"],
            yfinance_map={},
        )
        for sector in result.values():
            assert isinstance(sector, str)


# ---------------------------------------------------------------------------
# get_tickers_by_sector
# ---------------------------------------------------------------------------

class TestGetTickersBySector:
    def test_returns_list(self):
        result = get_tickers_by_sector("Information Technology")
        assert isinstance(result, list)

    def test_information_technology_contains_aapl(self):
        result = get_tickers_by_sector("Information Technology")
        assert "AAPL" in result

    def test_information_technology_contains_msft(self):
        result = get_tickers_by_sector("Information Technology")
        assert "MSFT" in result

    def test_communication_services_contains_googl(self):
        result = get_tickers_by_sector("Communication Services")
        assert "GOOGL" in result

    def test_unknown_sector_returns_empty_list(self):
        result = get_tickers_by_sector("Nonexistent Sector XYZ")
        assert result == []

    def test_all_returned_tickers_are_in_sector_map(self):
        result = get_tickers_by_sector("Financials")
        for ticker in result:
            assert SECTOR_MAP.get(ticker) == "Financials"

    def test_no_duplicates_in_result(self):
        result = get_tickers_by_sector("Information Technology")
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# is_valid_gics_sector
# ---------------------------------------------------------------------------

class TestIsValidGicsSector:
    def test_valid_sectors_return_true(self):
        for sector in GICS_SECTORS:
            assert is_valid_gics_sector(sector) is True

    def test_invalid_sector_returns_false(self):
        assert is_valid_gics_sector("Not A Sector") is False
        assert is_valid_gics_sector("") is False
        assert is_valid_gics_sector("Technology") is False  # Not exact GICS name

    def test_case_sensitive(self):
        """GICS sector names are case-sensitive."""
        assert is_valid_gics_sector("information technology") is False
        assert is_valid_gics_sector("Information Technology") is True


# ---------------------------------------------------------------------------
# normalise_sector_name
# ---------------------------------------------------------------------------

class TestNormaliseSectorName:
    def test_exact_gics_name_returned_unchanged(self):
        assert normalise_sector_name("Information Technology") == "Information Technology"
        assert normalise_sector_name("Health Care") == "Health Care"

    def test_alias_resolved_to_canonical_name(self):
        """Common aliases should be resolved to canonical GICS names."""
        assert normalise_sector_name("tech") == "Information Technology"
        assert normalise_sector_name("technology") == "Information Technology"
        assert normalise_sector_name("healthcare") == "Health Care"
        assert normalise_sector_name("pharma") == "Health Care"
        assert normalise_sector_name("banking") == "Financials"
        assert normalise_sector_name("energy") == "Energy"

    def test_case_insensitive_alias_lookup(self):
        """Alias lookup should be case-insensitive."""
        assert normalise_sector_name("TECH") == normalise_sector_name("tech")
        assert normalise_sector_name("Technology") == normalise_sector_name("technology")

    def test_unknown_alias_returns_original(self):
        """Unknown aliases should be returned as-is."""
        result = normalise_sector_name("completely_unknown_sector_xyz")
        assert result == "completely_unknown_sector_xyz"

    def test_empty_string_returns_empty(self):
        result = normalise_sector_name("")
        assert result == ""
