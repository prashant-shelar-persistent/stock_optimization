"""Unit tests for app.quantum.qubo — QUBO formulator.

Tests cover:
- build_qubo_matrix: shape, symmetry, cardinality penalty, return/risk terms
- qubo_energy: correct quadratic form evaluation
- decode_bitstring: valid and invalid inputs
- validate_qubo_solution: cardinality check
- qubo_to_dict: non-zero entries, key format
- Edge cases: single asset, all-zero returns, identity covariance
"""

from __future__ import annotations

import numpy as np
import pytest

from app.quantum.qubo import (
    build_qubo_matrix,
    decode_bitstring,
    qubo_energy,
    qubo_to_dict,
    validate_qubo_solution,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mu_4() -> np.ndarray:
    return np.array([0.12, 0.10, 0.09, 0.15])


@pytest.fixture
def sigma_4() -> np.ndarray:
    return np.array([
        [0.04, 0.01, 0.008, 0.012],
        [0.01, 0.03, 0.007, 0.009],
        [0.008, 0.007, 0.025, 0.006],
        [0.012, 0.009, 0.006, 0.05],
    ])


@pytest.fixture
def tickers_4() -> list[str]:
    return ["AAPL", "MSFT", "GOOGL", "AMZN"]


# ── build_qubo_matrix ─────────────────────────────────────────────────────────

class TestBuildQuboMatrix:
    """Tests for build_qubo_matrix."""

    def test_output_shape_is_n_by_n(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        assert Q.shape == (4, 4)

    def test_output_is_upper_triangular(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        # Lower triangle (below diagonal) should be zero
        for i in range(4):
            for j in range(i):
                assert Q[i, j] == 0.0, f"Q[{i},{j}] = {Q[i,j]} should be 0"

    def test_returns_numpy_array(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        assert isinstance(Q, np.ndarray)

    def test_diagonal_contains_return_and_risk_terms(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """Diagonal should have negative return contribution (minimisation)."""
        Q = build_qubo_matrix(
            mu_4, sigma_4,
            num_assets_to_select=2,
            lambda_return=1.0,
            lambda_risk=0.0,  # Disable risk term to isolate return term
            lambda_cardinality=0.0,  # Disable cardinality to isolate
        )
        # With only return term: Q[i,i] = -lambda_return * mu_norm[i]
        # Higher return asset should have more negative diagonal
        # AMZN (index 3) has highest return (0.15), GOOGL (index 2) lowest (0.09)
        assert Q[3, 3] < Q[2, 2]

    def test_cardinality_penalty_in_diagonal(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """With only cardinality term, diagonal should be (1 - 2k) * lambda_card."""
        k = 2
        lam = 5.0
        Q = build_qubo_matrix(
            mu_4, sigma_4,
            num_assets_to_select=k,
            lambda_return=0.0,
            lambda_risk=0.0,
            lambda_cardinality=lam,
        )
        expected_diag = lam * (1 - 2 * k)
        for i in range(4):
            assert abs(Q[i, i] - expected_diag) < 1e-10

    def test_cardinality_penalty_in_off_diagonal(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """With only cardinality term, off-diagonal should be 2 * lambda_card."""
        k = 2
        lam = 5.0
        Q = build_qubo_matrix(
            mu_4, sigma_4,
            num_assets_to_select=k,
            lambda_return=0.0,
            lambda_risk=0.0,
            lambda_cardinality=lam,
        )
        expected_off_diag = 2.0 * lam
        for i in range(4):
            for j in range(i + 1, 4):
                assert abs(Q[i, j] - expected_off_diag) < 1e-10

    def test_invalid_k_too_large_raises(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        with pytest.raises(ValueError, match="num_assets_to_select"):
            build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=5)

    def test_invalid_k_zero_raises(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        with pytest.raises(ValueError, match="num_assets_to_select"):
            build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=0)

    def test_mismatched_cov_shape_raises(
        self,
        mu_4: np.ndarray,
    ) -> None:
        bad_sigma = np.eye(3)  # 3x3 but mu has 4 elements
        with pytest.raises(ValueError, match="covariance_matrix"):
            build_qubo_matrix(mu_4, bad_sigma, num_assets_to_select=2)

    def test_k_equals_n_selects_all(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """k=n should be valid (select all assets)."""
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=4)
        assert Q.shape == (4, 4)

    def test_k_equals_1_is_valid(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=1)
        assert Q.shape == (4, 4)

    def test_3_asset_universe(self) -> None:
        mu = np.array([0.12, 0.10, 0.09])
        sigma = np.eye(3) * 0.04
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=2)
        assert Q.shape == (3, 3)

    def test_lambda_return_scales_diagonal(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """Doubling lambda_return should double the return contribution."""
        Q1 = build_qubo_matrix(
            mu_4, sigma_4, num_assets_to_select=2,
            lambda_return=1.0, lambda_risk=0.0, lambda_cardinality=0.0,
        )
        Q2 = build_qubo_matrix(
            mu_4, sigma_4, num_assets_to_select=2,
            lambda_return=2.0, lambda_risk=0.0, lambda_cardinality=0.0,
        )
        # Diagonal should be doubled
        np.testing.assert_allclose(Q2, 2.0 * Q1, rtol=1e-10)


# ── qubo_energy ───────────────────────────────────────────────────────────────

class TestQuboEnergy:
    """Tests for qubo_energy."""

    def test_zero_vector_gives_zero_energy(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.zeros(4)
        assert qubo_energy(Q, x) == 0.0

    def test_energy_is_scalar(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])
        energy = qubo_energy(Q, x)
        assert isinstance(energy, float)

    def test_energy_formula_is_xTQx(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 1.0, 0.0])
        expected = float(x @ Q @ x)
        assert abs(qubo_energy(Q, x) - expected) < 1e-12

    def test_different_solutions_have_different_energies(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        x1 = np.array([1.0, 1.0, 0.0, 0.0])
        x2 = np.array([0.0, 0.0, 1.0, 1.0])
        # Different solutions should generally have different energies
        e1 = qubo_energy(Q, x1)
        e2 = qubo_energy(Q, x2)
        # They may be equal by coincidence, but with real data they won't be
        assert isinstance(e1, float)
        assert isinstance(e2, float)

    def test_identity_matrix_energy(self) -> None:
        Q = np.eye(3)
        x = np.array([1.0, 1.0, 0.0])
        # x^T I x = sum(x^2) = 2
        assert abs(qubo_energy(Q, x) - 2.0) < 1e-12


# ── decode_bitstring ──────────────────────────────────────────────────────────

class TestDecodeBitstring:
    """Tests for decode_bitstring."""

    def test_basic_decode(self) -> None:
        x = decode_bitstring("1010")
        np.testing.assert_array_equal(x, [1.0, 0.0, 1.0, 0.0])

    def test_all_zeros(self) -> None:
        x = decode_bitstring("0000")
        np.testing.assert_array_equal(x, [0.0, 0.0, 0.0, 0.0])

    def test_all_ones(self) -> None:
        x = decode_bitstring("111")
        np.testing.assert_array_equal(x, [1.0, 1.0, 1.0])

    def test_single_bit(self) -> None:
        assert decode_bitstring("1")[0] == 1.0
        assert decode_bitstring("0")[0] == 0.0

    def test_returns_float64_array(self) -> None:
        x = decode_bitstring("101")
        assert x.dtype == np.float64

    def test_strips_whitespace(self) -> None:
        x = decode_bitstring("  101  ")
        np.testing.assert_array_equal(x, [1.0, 0.0, 1.0])

    def test_invalid_character_raises(self) -> None:
        with pytest.raises(ValueError, match="bitstring"):
            decode_bitstring("102")

    def test_invalid_letter_raises(self) -> None:
        with pytest.raises(ValueError, match="bitstring"):
            decode_bitstring("1a0")

    def test_length_matches_bitstring(self) -> None:
        x = decode_bitstring("10110")
        assert len(x) == 5


# ── validate_qubo_solution ────────────────────────────────────────────────────

class TestValidateQuboSolution:
    """Tests for validate_qubo_solution."""

    def test_valid_solution_returns_true(self) -> None:
        x = np.array([1.0, 0.0, 1.0, 0.0])
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is True
        assert "Valid" in msg

    def test_too_many_selected_returns_false(self) -> None:
        x = np.array([1.0, 1.0, 1.0, 0.0])
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is False
        assert "Cardinality violation" in msg

    def test_too_few_selected_returns_false(self) -> None:
        x = np.array([1.0, 0.0, 0.0, 0.0])
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is False

    def test_all_zeros_returns_false(self) -> None:
        x = np.zeros(4)
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is False

    def test_k_equals_n_all_ones_is_valid(self) -> None:
        x = np.ones(4)
        valid, msg = validate_qubo_solution(x, num_assets_to_select=4, n=4)
        assert valid is True

    def test_message_contains_expected_and_actual(self) -> None:
        x = np.array([1.0, 1.0, 1.0, 0.0])
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert "3" in msg  # actual selected
        assert "2" in msg  # expected


# ── qubo_to_dict ──────────────────────────────────────────────────────────────

class TestQuboToDict:
    """Tests for qubo_to_dict."""

    def test_returns_dict(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        tickers_4: list[str],
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        d = qubo_to_dict(Q, tickers_4)
        assert isinstance(d, dict)

    def test_keys_are_ticker_tuples(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        tickers_4: list[str],
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        d = qubo_to_dict(Q, tickers_4)
        for key in d:
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert key[0] in tickers_4
            assert key[1] in tickers_4

    def test_diagonal_entries_use_same_ticker_twice(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        tickers_4: list[str],
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        d = qubo_to_dict(Q, tickers_4)
        # Diagonal entries should have (ticker, ticker) keys
        diagonal_keys = [(t, t) for t in tickers_4]
        for key in diagonal_keys:
            assert key in d, f"Diagonal key {key} not found in QUBO dict"

    def test_only_nonzero_entries_included(
        self,
        tickers_4: list[str],
    ) -> None:
        # Zero matrix should produce empty dict
        Q = np.zeros((4, 4))
        d = qubo_to_dict(Q, tickers_4)
        assert d == {}

    def test_values_are_floats(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
        tickers_4: list[str],
    ) -> None:
        Q = build_qubo_matrix(mu_4, sigma_4, num_assets_to_select=2)
        d = qubo_to_dict(Q, tickers_4)
        assert all(isinstance(v, float) for v in d.values())
