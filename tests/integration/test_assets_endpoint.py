"""Integration tests for GET /api/v1/assets/search endpoint.

Tests cover:
1.  Exact ticker search returns matching result (AAPL → Apple Inc.)
2.  Result shape has required fields: ticker, name, sector, exchange
3.  AAPL returns Technology sector and NASDAQ exchange
4.  Search by company name fragment returns matching results
5.  Case-insensitive ticker search (lowercase == uppercase results)
6.  Ticker prefix search returns multiple matches (GOO → GOOGL + GOOG)
7.  limit parameter restricts result count
8.  limit=0 returns 422 (ge=1 constraint)
9.  limit=51 returns 422 (le=50 constraint)
10. Missing q parameter returns 422
11. Unknown ticker triggers yfinance fallback (mocked) and returns result
12. yfinance fallback returning None → empty list
13. Financials sector ticker (JPM) returns correct sector
14. Healthcare sector ticker (JNJ) returns correct sector
15. ETF ticker (SPY) returns ETF sector
16. Default limit is 10 — broad query returns at most 10 results
17. Well-known ticker returns non-null name field
18. Result list is a JSON array (not an object)
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Exact ticker search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_aapl_returns_result(client: AsyncClient) -> None:
    """Searching for 'AAPL' returns at least one result containing AAPL."""
    response = await client.get("/api/v1/assets/search?q=AAPL")

    assert response.status_code == 200
    results = response.json()
    assert isinstance(results, list)
    assert len(results) >= 1
    tickers = [r["ticker"] for r in results]
    assert "AAPL" in tickers


@pytest.mark.asyncio
async def test_search_result_shape(client: AsyncClient) -> None:
    """Each result has the required fields: ticker, name, sector, exchange."""
    response = await client.get("/api/v1/assets/search?q=MSFT")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1

    result = results[0]
    assert "ticker" in result, "Missing 'ticker' field"
    assert "name" in result, "Missing 'name' field"
    assert "sector" in result, "Missing 'sector' field"
    assert "exchange" in result, "Missing 'exchange' field"
    assert isinstance(result["ticker"], str)
    assert isinstance(result["name"], str)


@pytest.mark.asyncio
async def test_search_aapl_sector_and_exchange(client: AsyncClient) -> None:
    """AAPL search returns Technology sector and NASDAQ exchange."""
    response = await client.get("/api/v1/assets/search?q=AAPL")

    assert response.status_code == 200
    results = response.json()
    aapl = next((r for r in results if r["ticker"] == "AAPL"), None)
    assert aapl is not None, "AAPL not found in results"
    assert aapl["sector"] == "Technology"
    assert aapl["exchange"] == "NASDAQ"
    assert "Apple" in aapl["name"]


@pytest.mark.asyncio
async def test_search_msft_returns_microsoft(client: AsyncClient) -> None:
    """MSFT search returns Microsoft Corporation."""
    response = await client.get("/api/v1/assets/search?q=MSFT")

    assert response.status_code == 200
    results = response.json()
    msft = next((r for r in results if r["ticker"] == "MSFT"), None)
    assert msft is not None, "MSFT not found in results"
    assert "Microsoft" in msft["name"]
    assert msft["sector"] == "Technology"


# ---------------------------------------------------------------------------
# Company name search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_by_company_name_microsoft(client: AsyncClient) -> None:
    """Searching 'Microsoft' by name returns MSFT."""
    response = await client.get("/api/v1/assets/search?q=Microsoft")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    tickers = [r["ticker"] for r in results]
    assert "MSFT" in tickers


@pytest.mark.asyncio
async def test_search_by_company_name_apple(client: AsyncClient) -> None:
    """Searching 'Apple' by name returns AAPL."""
    response = await client.get("/api/v1/assets/search?q=Apple")

    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    tickers = [r["ticker"] for r in results]
    assert "AAPL" in tickers


# ---------------------------------------------------------------------------
# Case-insensitive search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_case_insensitive_ticker(client: AsyncClient) -> None:
    """Lowercase ticker query returns same results as uppercase."""
    response_upper = await client.get("/api/v1/assets/search?q=NVDA")
    response_lower = await client.get("/api/v1/assets/search?q=nvda")

    assert response_upper.status_code == 200
    assert response_lower.status_code == 200

    upper_tickers = {r["ticker"] for r in response_upper.json()}
    lower_tickers = {r["ticker"] for r in response_lower.json()}
    assert upper_tickers == lower_tickers


# ---------------------------------------------------------------------------
# Prefix search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_prefix_goo_returns_google_tickers(client: AsyncClient) -> None:
    """Searching 'GOO' prefix returns GOOGL and/or GOOG."""
    response = await client.get("/api/v1/assets/search?q=GOO")

    assert response.status_code == 200
    results = response.json()
    tickers = [r["ticker"] for r in results]
    assert "GOOGL" in tickers or "GOOG" in tickers, (
        f"Expected GOOGL or GOOG in results, got: {tickers}"
    )


# ---------------------------------------------------------------------------
# limit parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_limit_1_returns_at_most_1(client: AsyncClient) -> None:
    """limit=1 returns at most 1 result."""
    response = await client.get("/api/v1/assets/search?q=A&limit=1")

    assert response.status_code == 200
    results = response.json()
    assert len(results) <= 1


@pytest.mark.asyncio
async def test_search_limit_0_returns_422(client: AsyncClient) -> None:
    """limit=0 is invalid (ge=1) and returns HTTP 422."""
    response = await client.get("/api/v1/assets/search?q=AAPL&limit=0")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_limit_51_returns_422(client: AsyncClient) -> None:
    """limit=51 is invalid (le=50) and returns HTTP 422."""
    response = await client.get("/api/v1/assets/search?q=AAPL&limit=51")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_default_limit_is_10(client: AsyncClient) -> None:
    """Default limit is 10 — broad query returns at most 10 results."""
    # 'A' matches many tickers; default limit should cap at 10
    response = await client.get("/api/v1/assets/search?q=A")

    assert response.status_code == 200
    results = response.json()
    assert len(results) <= 10


# ---------------------------------------------------------------------------
# Missing query parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_missing_q_returns_422(client: AsyncClient) -> None:
    """Missing q parameter returns HTTP 422 validation error."""
    response = await client.get("/api/v1/assets/search")

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# yfinance fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_unknown_ticker_yfinance_fallback(client: AsyncClient) -> None:
    """Unknown ticker triggers yfinance fallback and returns the result."""
    mock_result = {
        "ticker": "XYZW",
        "name": "XYZ Widget Corp",
        "sector": "Industrials",
        "exchange": "NYSE",
    }

    with patch("app.api.v1.assets._lookup_yfinance", return_value=mock_result):
        response = await client.get("/api/v1/assets/search?q=XYZW")

    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["ticker"] == "XYZW"
    assert results[0]["name"] == "XYZ Widget Corp"
    assert results[0]["sector"] == "Industrials"
    assert results[0]["exchange"] == "NYSE"


@pytest.mark.asyncio
async def test_search_unknown_ticker_yfinance_returns_none(client: AsyncClient) -> None:
    """When yfinance returns None for unknown ticker, result is empty list."""
    with patch("app.api.v1.assets._lookup_yfinance", return_value=None):
        response = await client.get("/api/v1/assets/search?q=ZZZZZ")

    assert response.status_code == 200
    results = response.json()
    assert results == []


# ---------------------------------------------------------------------------
# Sector metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_jpm_returns_financials(client: AsyncClient) -> None:
    """JPM search returns Financials sector."""
    response = await client.get("/api/v1/assets/search?q=JPM")

    assert response.status_code == 200
    results = response.json()
    jpm = next((r for r in results if r["ticker"] == "JPM"), None)
    assert jpm is not None, "JPM not found in results"
    assert jpm["sector"] == "Financials"


@pytest.mark.asyncio
async def test_search_jnj_returns_healthcare(client: AsyncClient) -> None:
    """JNJ search returns Healthcare sector."""
    response = await client.get("/api/v1/assets/search?q=JNJ")

    assert response.status_code == 200
    results = response.json()
    jnj = next((r for r in results if r["ticker"] == "JNJ"), None)
    assert jnj is not None, "JNJ not found in results"
    assert jnj["sector"] == "Healthcare"


@pytest.mark.asyncio
async def test_search_spy_returns_etf(client: AsyncClient) -> None:
    """SPY search returns ETF sector."""
    response = await client.get("/api/v1/assets/search?q=SPY")

    assert response.status_code == 200
    results = response.json()
    spy = next((r for r in results if r["ticker"] == "SPY"), None)
    assert spy is not None, "SPY not found in results"
    assert spy["sector"] == "ETF"


# ---------------------------------------------------------------------------
# Response type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_response_is_list(client: AsyncClient) -> None:
    """Response body is a JSON array (not an object)."""
    response = await client.get("/api/v1/assets/search?q=AAPL")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list), f"Expected list, got {type(body).__name__}"


@pytest.mark.asyncio
async def test_search_well_known_ticker_has_nonempty_name(client: AsyncClient) -> None:
    """Well-known ticker returns a non-null, non-empty name field."""
    response = await client.get("/api/v1/assets/search?q=AMZN")

    assert response.status_code == 200
    results = response.json()
    amzn = next((r for r in results if r["ticker"] == "AMZN"), None)
    assert amzn is not None, "AMZN not found in results"
    assert amzn["name"] is not None
    assert len(amzn["name"]) > 0
