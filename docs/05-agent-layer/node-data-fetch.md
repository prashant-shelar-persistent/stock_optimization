# Node: Data Fetch

`data_fetch_node` is the **first node** in the optimization pipeline and the only one that communicates with external services (yfinance and Redis). It fetches historical price data, computes log returns and the covariance matrix, and populates the sector map.

**Source files:**
- Node: `backend/app/agents/nodes.py` — `data_fetch_node()`
- Data layer: `backend/app/data/fetcher.py` — `fetch_market_data()`

## Responsibility

```
data_fetch_node
    └── fetch_market_data(tickers, lookback_days)
            ├── Redis cache lookup
            ├── yfinance batch download (with retry)
            ├── Per-ticker fallback (if batch fails)
            ├── NaN filtering and forward-fill
            ├── Log returns computation
            ├── Annualised expected returns + covariance
            ├── PSD correction on covariance matrix
            ├── Sector metadata fetch
            └── Redis cache write
```

## Node Signature

```python
def data_fetch_node(state: AgentState) -> AgentState:
    """Fetch historical price data and compute returns/covariance."""
```

**Reads from state:** `tickers`, `request_params` (for `lookback_days`)

**Writes to state:** `price_data`, `returns_data`, `expected_returns`, `covariance_matrix`, `sector_map`, `tickers` (updated), `node_timings_ms`, `completed_nodes`

**Fatal on failure:** Yes — sets `state["error"]` and `state["failed_node"]`, causing the graph to route to `END`.

## `MarketData` Dataclass

`fetch_market_data()` returns a `MarketData` dataclass defined in `backend/app/data/fetcher.py`:

```python
@dataclass
class MarketData:
    valid_tickers: list[str]          # Tickers that survived data quality filter
    price_data: pd.DataFrame          # Adjusted close prices (days × n_assets)
    returns_data: pd.DataFrame        # Daily log returns (days-1 × n_assets)
    expected_returns: np.ndarray      # Annualised expected returns (n_assets,)
    covariance_matrix: np.ndarray     # Annualised covariance matrix (n × n)
    sector_map: dict[str, str]        # ticker → sector name
    fetch_timestamp: datetime         # UTC timestamp of the fetch
    metadata: dict[str, dict[str, Any]]  # Per-ticker name/exchange/currency
```

## yfinance Call

The node calls `yfinance.download()` with `auto_adjust=True` to get split/dividend-adjusted close prices. A batch download is attempted first; if it returns empty, a per-ticker fallback using `Ticker.history()` is used:

```python
raw = yf.download(
    tickers=tickers,
    start=start_str,
    end=end_str,
    auto_adjust=True,
    progress=False,
    threads=False,
)
```

> **Important:** A custom `curl_cffi` session is deliberately **not** passed to `yf.download()`. Custom sessions trigger HTTP 429 (Too Many Requests) from Yahoo Finance. Plain `yf.download()` uses yfinance's built-in cookie/crumb handling.

The download is retried up to 3 times with exponential back-off (5 s, 10 s, 20 s) on transient failures.

## Log Returns Computation

Daily log returns are computed as:

```
r_t = ln(P_t / P_{t-1})
```

In code:

```python
returns_data = np.log(price_data / price_data.shift(1)).dropna()
```

This produces a DataFrame of shape `(days-1, n_assets)`.

## Annualised Statistics

Expected returns and the covariance matrix are annualised by multiplying by the number of trading days per year (252):

```python
TRADING_DAYS_PER_YEAR = 252

expected_returns = returns_data.mean().values * TRADING_DAYS_PER_YEAR
covariance_matrix = returns_data.cov().values * TRADING_DAYS_PER_YEAR
```

### PSD Correction

The covariance matrix is guaranteed to be positive semi-definite (PSD) by clipping negative eigenvalues to zero:

```python
def _ensure_psd(matrix: np.ndarray) -> np.ndarray:
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    eigenvalues = np.maximum(eigenvalues, 0)
    return eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T
```

This prevents CVXPY from rejecting the covariance matrix as non-PSD when numerical noise produces tiny negative eigenvalues.

## Data Quality Filtering

Before computing returns, tickers with too many missing values are dropped:

```python
MAX_NAN_FRACTION = 0.20   # Drop tickers with > 20% NaN values
MIN_TRADING_DAYS = 30     # Require at least 30 trading days

min_valid_rows = int((1.0 - MAX_NAN_FRACTION) * len(price_data))
price_data = price_data.dropna(axis=1, thresh=min_valid_rows)
```

Remaining NaN values are forward-filled then back-filled:

```python
price_data = price_data.ffill().bfill()
```

The `tickers` field in state is updated to reflect only the valid tickers after filtering.

## Sector Map Population

After fetching prices, `_fetch_ticker_metadata()` calls `yf.Ticker(ticker).info` for each ticker to retrieve the `sector` field. The result is stored as a `dict[str, str]`:

```python
sector_map = {"AAPL": "Technology", "JPM": "Financial Services", ...}
```

If the yfinance metadata call fails for a ticker, that ticker is assigned `"Unknown"` sector. The sector map is later injected into `validated_constraints` by the constraint validation node.

## Redis Cache Key Strategy

Cache keys are deterministic SHA-256 hashes of the sorted ticker list and lookback period:

```python
def _make_cache_key(tickers: list[str], lookback_days: int) -> str:
    key_data = json.dumps({"tickers": sorted(tickers), "lookback_days": lookback_days})
    return "market_data:" + hashlib.sha256(key_data.encode()).hexdigest()
```

The `MarketData` object is serialised with `pickle` and stored in Redis with a TTL of `CACHE_TTL_SECONDS` (default: 3600 seconds / 1 hour):

```python
r.setex(cache_key, ttl, pickle.dumps(market_data))
```

On a cache hit, the node skips the yfinance call entirely and returns the cached `MarketData` directly. Cache failures (Redis unavailable) are silently ignored — the node falls back to a live fetch.

## Error Handling

The node wraps the entire `fetch_market_data()` call in a `try/except`:

```python
try:
    market_data = fetch_market_data(tickers=tickers, lookback_days=lookback_days)
except Exception as exc:
    updated = dict(state)
    updated["error"] = str(exc)
    updated["failed_node"] = "data_fetch"
    updated["error_details"] = {
        "node": "data_fetch",
        "error_type": type(exc).__name__,
        "tickers": tickers,
    }
    _record_timing(updated, "data_fetch", elapsed_ms)
    return updated
```

A `DataFetchError` is raised by `fetch_market_data()` in these cases:
- No price data returned for any ticker
- All tickers dropped due to > 20% NaN values
- Fewer than 30 trading days available after cleaning
- Returns DataFrame is empty after NaN removal

Because `data_fetch_node` is a **fatal** node, any error here causes the graph to route immediately to `END` via `_route_after_fatal_node()`. No downstream nodes execute.

## State Updates on Success

```python
updated["price_data"]        = market_data.price_data
updated["returns_data"]      = market_data.returns_data
updated["expected_returns"]  = market_data.expected_returns
updated["covariance_matrix"] = market_data.covariance_matrix
updated["sector_map"]        = market_data.sector_map
updated["tickers"]           = market_data.valid_tickers  # may differ from input
```

## Related Pages

- [Agent State](agent-state.md) — Full state field reference
- [Node: Constraint Validation](node-constraint-validation.md) — Consumes `expected_returns`, `covariance_matrix`, `sector_map`
- [Error Routing](error-routing.md) — How data fetch failure routes to END
