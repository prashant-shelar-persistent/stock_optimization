"""Unit tests for app.data.sector_tags — sector tagging utilities.

Tests cover:
- get_sector: known tickers, unknown tickers, case-insensitivity
- enrich_sector_map: priority order (yfinance > static > fallback)
- get_tickers_by_sector: known sector, unknown sector
- is_valid_gics_sector: valid and invalid sector names
- normalise_sector_name: common aliases
- GICS_SECTORS constant: completeness check
"""

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


# ── get_sector ────────────────────────────────────────────────────────────────

class TestGetSector:
    """Tests for get_sector."""

    def test_known_ticker_aapl(self) -> None:
        assert get_sector("AAPL") == "Information Technology"

    def test_known_ticker_msft(self) -> None:
        assert get_sector("MSFT") == "Information Technology"

    def test_known_ticker_googl(self) -> None:
        assert get_sector("GOOGL") == "Communication Services"

    def test_known_ticker_amzn(self) -> None:
        assert get_sector("AMZN") == "Consumer Discretionary"

    def test_unknown_ticker_returns_default_fallback(self) -> None:
        assert get_sector("XYZNOTREAL") == "Unknown"

    def test_custom_fallback_value(self) -> None:
        assert get_sector("XYZNOTREAL", fallback="N/A") == "N/A"

    def test_case_insensitive_lowercase(self) -> None:
        assert get_sector("aapl") == "Information Technology"

    def test_case_insensitive_mixed(self) -> None:
        assert get_sector("Msft") == "Information Technology"

    def test_strips_whitespace(self) -> None:
        assert get_sector("  AAPL  ") == "Information Technology"

    def test_empty_string_returns_fallback(self) -> None:
        assert get_sector("") == "Unknown"


# ── enrich_sector_map ─────────────────────────────────────────────────────────

class TestEnrichSectorMap:
    """Tests for enrich_sector_map."""

    def test_static_map_used_for_known_tickers(self) -> None:
        result = enrich_sector_map(["AAPL", "MSFT"])
        assert result["AAPL"] == "Information Technology"
        assert result["MSFT"] == "Information Technology"

    def test_yfinance_map_takes_priority_over_static(self) -> None:
        # yfinance says AAPL is "Technology" — should override static map
        result = enrich_sector_map(["AAPL"], yfinance_map={"AAPL": "Technology"})
        assert result["AAPL"] == "Technology"

    def test_static_map_used_when_yfinance_missing(self) -> None:
        result = enrich_sector_map(["AAPL"], yfinance_map={"MSFT": "Technology"})
        assert result["AAPL"] == "Information Technology"

    def test_unknown_ticker_falls_back_to_unknown(self) -> None:
        result = enrich_sector_map(["XYZNOTREAL"])
        assert result["XYZNOTREAL"] == "Unknown"

    def test_yfinance_unknown_value_falls_through_to_static(self) -> None:
        # yfinance returns "Unknown" — should fall through to static map
        result = enrich_sector_map(["AAPL"], yfinance_map={"AAPL": "Unknown"})
        assert result["AAPL"] == "Information Technology"

    def test_yfinance_empty_string_falls_through_to_static(self) -> None:
        result = enrich_sector_map(["AAPL"], yfinance_map={"AAPL": ""})
        assert result["AAPL"] == "Information Technology"

    def test_empty_tickers_list_returns_empty_dict(self) -> None:
        result = enrich_sector_map([])
        assert result == {}

    def test_no_yfinance_map_uses_static_only(self) -> None:
        result = enrich_sector_map(["AAPL", "MSFT", "GOOGL"])
        assert len(result) == 3
        assert all(v != "Unknown" for v in result.values())

    def test_result_keys_are_uppercase(self) -> None:
        result = enrich_sector_map(["aapl", "msft"])
        assert "AAPL" in result
        assert "MSFT" in result

    def test_mixed_known_and_unknown_tickers(self) -> None:
        result = enrich_sector_map(["AAPL", "XYZNOTREAL"])
        assert result["AAPL"] == "Information Technology"
        assert result["XYZNOTREAL"] == "Unknown"


# ── get_tickers_by_sector ─────────────────────────────────────────────────────

class TestGetTickersBySector:
    """Tests for get_tickers_by_sector."""

    def test_information_technology_contains_aapl(self) -> None:
        tickers = get_tickers_by_sector("Information Technology")
        assert "AAPL" in tickers

    def test_information_technology_contains_msft(self) -> None:
        tickers = get_tickers_by_sector("Information Technology")
        assert "MSFT" in tickers

    def test_communication_services_contains_googl(self) -> None:
        tickers = get_tickers_by_sector("Communication Services")
        assert "GOOGL" in tickers

    def test_unknown_sector_returns_empty_list(self) -> None:
        tickers = get_tickers_by_sector("Nonexistent Sector XYZ")
        assert tickers == []

    def test_result_is_sorted(self) -> None:
        tickers = get_tickers_by_sector("Information Technology")
        assert tickers == sorted(tickers)

    def test_case_insensitive_lookup(self) -> None:
        tickers_upper = get_tickers_by_sector("Information Technology")
        tickers_lower = get_tickers_by_sector("information technology")
        assert tickers_upper == tickers_lower

    def test_energy_sector_has_tickers(self) -> None:
        tickers = get_tickers_by_sector("Energy")
        assert len(tickers) > 0


# ── is_valid_gics_sector ──────────────────────────────────────────────────────

class TestIsValidGicsSector:
    """Tests for is_valid_gics_sector."""

    @pytest.mark.parametrize("sector", [
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
    ])
    def test_all_11_gics_sectors_are_valid(self, sector: str) -> None:
        assert is_valid_gics_sector(sector) is True

    def test_invalid_sector_returns_false(self) -> None:
        assert is_valid_gics_sector("Technology") is False

    def test_empty_string_is_invalid(self) -> None:
        assert is_valid_gics_sector("") is False

    def test_partial_match_is_invalid(self) -> None:
        assert is_valid_gics_sector("Information") is False

    def test_strips_whitespace(self) -> None:
        assert is_valid_gics_sector("  Energy  ") is True


# ── normalise_sector_name ─────────────────────────────────────────────────────

class TestNormaliseSectorName:
    """Tests for normalise_sector_name."""

    def test_technology_maps_to_information_technology(self) -> None:
        assert normalise_sector_name("Technology") == "Information Technology"

    def test_healthcare_maps_to_health_care(self) -> None:
        result = normalise_sector_name("Healthcare")
        assert result == "Health Care"

    def test_telecom_maps_to_communication_services(self) -> None:
        result = normalise_sector_name("Telecom")
        assert result == "Communication Services"

    def test_unknown_alias_returns_original(self) -> None:
        result = normalise_sector_name("Completely Unknown Sector XYZ")
        assert result == "Completely Unknown Sector XYZ"

    def test_case_insensitive_alias_lookup(self) -> None:
        result = normalise_sector_name("technology")
        assert result == "Information Technology"

    def test_energy_alias(self) -> None:
        result = normalise_sector_name("energy")
        assert result == "Energy"


# ── GICS_SECTORS constant ─────────────────────────────────────────────────────

class TestGicsSectors:
    """Tests for the GICS_SECTORS constant."""

    def test_has_exactly_11_sectors(self) -> None:
        assert len(GICS_SECTORS) == 11

    def test_is_frozenset(self) -> None:
        assert isinstance(GICS_SECTORS, frozenset)

    def test_contains_information_technology(self) -> None:
        assert "Information Technology" in GICS_SECTORS

    def test_contains_health_care(self) -> None:
        assert "Health Care" in GICS_SECTORS


# ── SECTOR_MAP constant ───────────────────────────────────────────────────────

class TestSectorMap:
    """Tests for the SECTOR_MAP constant."""

    def test_is_dict(self) -> None:
        assert isinstance(SECTOR_MAP, dict)

    def test_all_values_are_valid_gics_sectors(self) -> None:
        invalid = [
            (ticker, sector)
            for ticker, sector in SECTOR_MAP.items()
            if sector not in GICS_SECTORS
        ]
        assert invalid == [], f"Invalid sectors found: {invalid[:5]}"

    def test_all_keys_are_uppercase(self) -> None:
        non_upper = [k for k in SECTOR_MAP if k != k.upper()]
        assert non_upper == [], f"Non-uppercase keys: {non_upper[:5]}"

    def test_has_many_entries(self) -> None:
        # Should have at least 100 well-known tickers
        assert len(SECTOR_MAP) >= 100
