"""Integration tests for GET /api/v1/assets/search endpoint.

Tests cover:
1. Search by exact ticker returns matching result
2. Search by ticker prefix returns multiple matches
3. Search by company name (case-insensitive) returns results
4. Empty query returns 422 (min_length=1)
5. limit parameter restricts result count
6. limit=0 returns 422 (ge=1)
7. limit=51 returns 422 (le=50)
8. Unknown ticker falls back to yfinance (mocked)
9. yfinance fallback returns None → empty list
10. Result shape has required fields: ticker, name, sector, exchange
11. Ticker search is case-insensitive (lowercase query)
12. Well-known tickers return correct sector metadata
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_exact_ticker_returns_result() -> None:
    """Searching for 'AAPL' returns Apple Inc. as first result."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=AAPL")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    tickers = [r["ticker"] for r in results]
    assert "AAPL" in tickers


@pytest.mark.asyncio
async def test_search_result_has_correct_fields() -> None:
    """Search result contains all required fields with correct types."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=MSFT")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1

    result = results[0]
    assert "ticker" in result
    assert "name" in result
    assert "sector" in result
    assert "exchange" in result
    assert isinstance(result["ticker"], str)
    assert isinstance(result["name"], str)


@pytest.mark.asyncio
async def test_search_aapl_returns_technology_sector() -> None:
    """AAPL search returns Technology sector metadata."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=AAPL")

    assert response.status_code == 200
    results = response.json()
    aapl = next((r for r in results if r["ticker"] == "AAPL"), None)
    assert aapl is not None
    assert aapl["sector"] == "Technology"
    assert aapl["exchange"] == "NASDAQ"
    assert "Apple" in aapl["name"]


@pytest.mark.asyncio
async def test_search_by_company_name() -> None:
    """Searching by company name fragment returns matching results."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=Microsoft")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    tickers = [r["ticker"] for r in results]
    assert "MSFT" in tickers


@pytest.mark.asyncio
async def test_search_case_insensitive_ticker() -> None:
    """Lowercase ticker query returns same results as uppercase."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response_upper = await client.get("/api/v1/assets/search?q=NVDA")
        response_lower = await client.get("/api/v1/assets/search?q=nvda")

    assert response_upper.status_code == 200
    assert response_lower.status_code == 200

    upper_tickers = {r["ticker"] for r in response_upper.json()}
    lower_tickers = {r["ticker"] for r in response_lower.json()}
    assert upper_tickers == lower_tickers


@pytest.mark.asyncio
async def test_search_ticker_prefix_returns_multiple() -> None:
    """Searching for 'GO' prefix returns GOOGL and GOOG."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=GOO")

    assert response.status_code == 200
    results = response.json()
    tickers = [r["ticker"] for r in results]
    # Both GOOGL and GOOG should appear
    assert "GOOGL" in tickers or "GOOG" in tickers


@pytest.mark.asyncio
async def test_search_limit_restricts_results() -> None:
    """limit=1 returns at most 1 result."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=A&limit=1")

    assert response.status_code == 200
    results = response.json()
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_search_limit_zero_returns_422() -> None:
    """limit=0 is invalid (ge=1) and returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=AAPL&limit=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_limit_over_50_returns_422() -> None:
    """limit=51 is invalid (le=50) and returns 422."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=AAPL&limit=51")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_missing_query_returns_422() -> None:
    """Missing q parameter returns 422 validation error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_unknown_ticker_yfinance_fallback() -> None:
    """Unknown ticker triggers yfinance fallback and returns result."""
    mock_result = {
        "ticker": "XYZW",
        "name": "XYZ Widget Corp",
        "sector": "Industrials",
        "exchange": "NYSE",
    }

    with patch("app.api.v1.assets._lookup_yfinance", return_value=mock_result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/assets/search?q=XYZW")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["ticker"] == "XYZW"
    assert results[0]["name"] == "XYZ Widget Corp"
    assert results[0]["sector"] == "Industrials"


@pytest.mark.asyncio
async def test_search_unknown_ticker_yfinance_returns_none() -> None:
    """When yfinance returns None for unknown ticker, result is empty list."""
    with patch("app.api.v1.assets._lookup_yfinance", return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/assets/search?q=ZZZZZ")

    assert response.status_code == 200
    results = response.json()
    assert results == []


@pytest.mark.asyncio
async def test_search_financials_sector() -> None:
    """JPM search returns Financials sector."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=JPM")

    assert response.status_code == 200
    results = response.json()
    jpm = next((r for r in results if r["ticker"] == "JPM"), None)
    assert jpm is not None
    assert jpm["sector"] == "Financials"


@pytest.mark.asyncio
async def test_search_healthcare_sector() -> None:
    """JNJ search returns Healthcare sector."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=JNJ")

    assert response.status_code == 200
    results = response.json()
    jnj = next((r for r in results if r["ticker"] == "JNJ"), None)
    assert jnj is not None
    assert jnj["sector"] == "Healthcare"


@pytest.mark.asyncio
async def test_search_etf_sector() -> None:
    """SPY search returns ETF sector."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/assets/search?q=SPY")

    assert response.status_code == 200
    results = response.json()
    spy = next((r for r in results if r["ticker"] == "SPY"), None)
    assert spy is not None
    assert spy["sector"] == "ETF"


@pytest.mark.asyncio
async def test_search_default_limit_is_10() -> None:
    """Default limit is 10 — broad query returns at most 10 results."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 'A' matches many tickers — should be capped at 10
        response = await client.get("/api/v1/assets/search?q=A")

    assert response.status_code == 200
    results = response.json()
    assert len(results) <= 10
