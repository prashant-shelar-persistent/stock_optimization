"""Shared pytest fixtures for all test modules.

Provides reusable numpy arrays, DataFrames, and schema objects that are
used across multiple test files.
"""

import numpy as np
import pandas as pd
import pytest


# ── Deterministic random seed ─────────────────────────────────────────────────
RNG = np.random.default_rng(seed=42)


# ── Small 3-asset universe ─────────────────────────────────────────────────────

@pytest.fixture
def tickers_3() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL"]


@pytest.fixture
def expected_returns_3() -> np.ndarray:
    """Annualised expected returns for 3 assets."""
    return np.array([0.12, 0.10, 0.09])


@pytest.fixture
def cov_matrix_3() -> np.ndarray:
    """Annualised covariance matrix for 3 assets (positive definite)."""
    return np.array([
        [0.04, 0.01, 0.008],
        [0.01, 0.03, 0.007],
        [0.008, 0.007, 0.025],
    ])


@pytest.fixture
def returns_df_3(cov_matrix_3: np.ndarray) -> pd.DataFrame:
    """250 days of simulated daily log returns for 3 assets."""
    rng = np.random.default_rng(seed=0)
    daily_cov = cov_matrix_3 / 252
    daily_returns = rng.multivariate_normal(
        mean=[0.12 / 252, 0.10 / 252, 0.09 / 252],
        cov=daily_cov,
        size=250,
    )
    return pd.DataFrame(daily_returns, columns=["AAPL", "MSFT", "GOOGL"])


# ── 4-asset universe ───────────────────────────────────────────────────────────

@pytest.fixture
def tickers_4() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL", "AMZN"]


@pytest.fixture
def expected_returns_4() -> np.ndarray:
    return np.array([0.12, 0.10, 0.09, 0.15])


@pytest.fixture
def cov_matrix_4() -> np.ndarray:
    """Annualised covariance matrix for 4 assets (positive definite)."""
    return np.array([
        [0.04, 0.01, 0.008, 0.012],
        [0.01, 0.03, 0.007, 0.009],
        [0.008, 0.007, 0.025, 0.006],
        [0.012, 0.009, 0.006, 0.05],
    ])


@pytest.fixture
def sector_tags_4() -> dict[str, str]:
    return {
        "AAPL": "Information Technology",
        "MSFT": "Information Technology",
        "GOOGL": "Communication Services",
        "AMZN": "Consumer Discretionary",
    }


# ── Chat rate-limit bucket reset ──────────────────────────────────────────────
# The in-process rate limiter in app.api.v1.chat uses a module-level dict.
# Clear it before each test so rate-limit state does not leak between tests.

@pytest.fixture(autouse=True)
def reset_chat_rate_limit_buckets() -> None:
    """Clear the in-process rate-limit bucket before each test."""
    try:
        from app.api.v1.chat import _rate_limit_buckets  # noqa: PLC0415
        _rate_limit_buckets.clear()
    except ImportError:
        pass
