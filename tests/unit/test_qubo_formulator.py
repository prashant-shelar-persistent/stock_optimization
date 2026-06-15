"""Unit tests for app.quantum.qubo and app.engines.quantum.qubo.

Tests cover:
- build_qubo_matrix: shape, symmetry, cardinality penalty
- qubo_energy: correct quadratic form evaluation
- decode_bitstring: valid and invalid inputs
- validate_qubo_solution: cardinality check
- qubo_to_dict: dictionary representation
- build_qubo (engines layer): metadata correctness
- evaluate_solution: wrapper around qubo_energy
- find_best_bitstring: finds minimum energy sample
- enumerate_all_solutions: brute-force enumeration
- compute_approximation_ratio: ratio computation
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
from app.engines.quantum.qubo import (
    QUBOMetadata,
    build_qubo,
    compute_approximation_ratio,
    enumerate_all_solutions,
    evaluate_solution,
    find_best_bitstring,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_simple_inputs(n: int = 4, k: int = 2):
    """Return simple expected_returns and covariance_matrix for n assets."""
    rng = np.random.default_rng(42)
    mu = rng.uniform(0.05, 0.20, n)
    A = rng.normal(0, 0.1, (n, n))
    sigma = A @ A.T + np.eye(n) * 0.01
    return mu, sigma, k


# ---------------------------------------------------------------------------
# build_qubo_matrix
# ---------------------------------------------------------------------------

class TestBuildQuboMatrix:
    def test_output_shape_is_n_by_n(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=k)
        assert Q.shape == (4, 4)

    def test_output_is_upper_triangular(self):
        """The QUBO matrix should be upper-triangular (lower triangle is zero)."""
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=k)
        # Lower triangle (excluding diagonal) should be zero
        for i in range(4):
            for j in range(i):
                assert Q[i, j] == 0.0, f"Q[{i},{j}] = {Q[i,j]} should be 0"

    def test_diagonal_contains_linear_terms(self):
        """Diagonal entries should be non-zero (linear terms from return + risk + cardinality)."""
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=k)
        # At least some diagonal entries should be non-zero
        assert np.any(np.diag(Q) != 0.0)

    def test_invalid_k_too_large_raises_value_error(self):
        mu, sigma, _ = _make_simple_inputs(n=3)
        with pytest.raises(ValueError, match="num_assets_to_select"):
            build_qubo_matrix(mu, sigma, num_assets_to_select=5)  # k > n

    def test_invalid_k_zero_raises_value_error(self):
        mu, sigma, _ = _make_simple_inputs(n=3)
        with pytest.raises(ValueError, match="num_assets_to_select"):
            build_qubo_matrix(mu, sigma, num_assets_to_select=0)  # k < 1

    def test_mismatched_sigma_shape_raises_value_error(self):
        mu = np.array([0.10, 0.08, 0.12])
        sigma = np.eye(4)  # Wrong shape: (4,4) for 3 assets
        with pytest.raises(ValueError, match="covariance_matrix"):
            build_qubo_matrix(mu, sigma, num_assets_to_select=2)

    def test_cardinality_penalty_affects_diagonal(self):
        """Higher lambda_cardinality should change diagonal values."""
        mu, sigma, k = _make_simple_inputs(n=3, k=1)
        Q_low = build_qubo_matrix(mu, sigma, k, lambda_cardinality=1.0)
        Q_high = build_qubo_matrix(mu, sigma, k, lambda_cardinality=10.0)
        # Diagonal should differ
        assert not np.allclose(np.diag(Q_low), np.diag(Q_high))

    def test_return_penalty_affects_diagonal(self):
        """Higher lambda_return should change diagonal values."""
        mu, sigma, k = _make_simple_inputs(n=3, k=1)
        Q_low = build_qubo_matrix(mu, sigma, k, lambda_return=0.5)
        Q_high = build_qubo_matrix(mu, sigma, k, lambda_return=2.0)
        assert not np.allclose(np.diag(Q_low), np.diag(Q_high))

    def test_k_equals_n_selects_all_assets(self):
        """When k=n, the cardinality penalty should push toward selecting all assets."""
        n = 3
        mu, sigma, _ = _make_simple_inputs(n=n)
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=n)
        # All-ones vector should have low energy (satisfies cardinality)
        x_all = np.ones(n)
        energy_all = qubo_energy(Q, x_all)
        # Compare to a partial selection
        x_partial = np.array([1.0, 0.0, 0.0])
        energy_partial = qubo_energy(Q, x_partial)
        # All-ones should have lower energy (cardinality penalty = 0)
        assert energy_all < energy_partial


# ---------------------------------------------------------------------------
# qubo_energy
# ---------------------------------------------------------------------------

class TestQuboEnergy:
    def test_zero_vector_gives_zero_energy(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q = build_qubo_matrix(mu, sigma, k)
        x = np.zeros(4)
        energy = qubo_energy(Q, x)
        assert energy == 0.0

    def test_energy_is_scalar(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q = build_qubo_matrix(mu, sigma, k)
        x = np.array([1.0, 0.0, 1.0, 0.0])
        energy = qubo_energy(Q, x)
        assert isinstance(energy, float)

    def test_energy_formula_x_T_Q_x(self):
        """qubo_energy should compute x^T Q x."""
        Q = np.array([[1.0, 2.0], [0.0, 3.0]])
        x = np.array([1.0, 1.0])
        expected = float(x @ Q @ x)  # 1*1 + 1*2 + 0*1 + 1*3 = 6
        result = qubo_energy(Q, x)
        assert abs(result - expected) < 1e-10

    def test_energy_with_known_values(self):
        """Verify energy for a simple 2x2 QUBO."""
        Q = np.array([[2.0, 1.0], [0.0, 3.0]])
        x = np.array([1.0, 0.0])
        # x^T Q x = [1,0] @ [[2,1],[0,3]] @ [1,0] = [2,1] @ [1,0] = 2
        result = qubo_energy(Q, x)
        assert abs(result - 2.0) < 1e-10


# ---------------------------------------------------------------------------
# decode_bitstring
# ---------------------------------------------------------------------------

class TestDecodeBitstring:
    def test_valid_bitstring_decoded_correctly(self):
        result = decode_bitstring("10110")
        expected = np.array([1.0, 0.0, 1.0, 1.0, 0.0])
        np.testing.assert_array_equal(result, expected)

    def test_all_zeros(self):
        result = decode_bitstring("000")
        np.testing.assert_array_equal(result, np.zeros(3))

    def test_all_ones(self):
        result = decode_bitstring("111")
        np.testing.assert_array_equal(result, np.ones(3))

    def test_single_bit(self):
        assert decode_bitstring("1")[0] == 1.0
        assert decode_bitstring("0")[0] == 0.0

    def test_whitespace_stripped(self):
        result = decode_bitstring("  101  ")
        expected = np.array([1.0, 0.0, 1.0])
        np.testing.assert_array_equal(result, expected)

    def test_invalid_character_raises_value_error(self):
        with pytest.raises(ValueError, match="bitstring"):
            decode_bitstring("10210")

    def test_invalid_letter_raises_value_error(self):
        with pytest.raises(ValueError, match="bitstring"):
            decode_bitstring("1a0")

    def test_output_dtype_is_float64(self):
        result = decode_bitstring("101")
        assert result.dtype == np.float64

    def test_output_length_matches_bitstring(self):
        for length in [1, 3, 5, 8]:
            bitstring = "1" * length
            result = decode_bitstring(bitstring)
            assert len(result) == length


# ---------------------------------------------------------------------------
# validate_qubo_solution
# ---------------------------------------------------------------------------

class TestValidateQuboSolution:
    def test_valid_solution_returns_true(self):
        x = np.array([1.0, 0.0, 1.0, 0.0])
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is True
        assert "Valid" in msg

    def test_too_many_selected_returns_false(self):
        x = np.array([1.0, 1.0, 1.0, 0.0])  # 3 selected, expected 2
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is False
        assert "Cardinality violation" in msg

    def test_too_few_selected_returns_false(self):
        x = np.array([1.0, 0.0, 0.0, 0.0])  # 1 selected, expected 2
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is False

    def test_all_zeros_returns_false_when_k_positive(self):
        x = np.zeros(4)
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is False

    def test_message_contains_expected_count(self):
        x = np.array([1.0, 1.0, 1.0])  # 3 selected, expected 2
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=3)
        assert "2" in msg  # Expected count


# ---------------------------------------------------------------------------
# qubo_to_dict
# ---------------------------------------------------------------------------

class TestQuboToDict:
    def test_returns_dict(self):
        mu, sigma, k = _make_simple_inputs(n=3, k=2)
        Q = build_qubo_matrix(mu, sigma, k)
        tickers = ["AAPL", "MSFT", "GOOGL"]
        result = qubo_to_dict(Q, tickers)
        assert isinstance(result, dict)

    def test_keys_are_ticker_tuples(self):
        mu, sigma, k = _make_simple_inputs(n=3, k=2)
        Q = build_qubo_matrix(mu, sigma, k)
        tickers = ["AAPL", "MSFT", "GOOGL"]
        result = qubo_to_dict(Q, tickers)
        for key in result:
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert key[0] in tickers
            assert key[1] in tickers

    def test_only_nonzero_entries_included(self):
        """Zero entries should not appear in the dict."""
        Q = np.array([[1.0, 0.0], [0.0, 2.0]])  # Off-diagonal is zero
        tickers = ["A", "B"]
        result = qubo_to_dict(Q, tickers)
        # Only diagonal entries should be present
        assert ("A", "B") not in result

    def test_diagonal_entries_use_same_ticker_twice(self):
        Q = np.array([[1.0, 0.5], [0.0, 2.0]])
        tickers = ["A", "B"]
        result = qubo_to_dict(Q, tickers)
        assert ("A", "A") in result
        assert ("B", "B") in result


# ---------------------------------------------------------------------------
# build_qubo (engines layer)
# ---------------------------------------------------------------------------

class TestBuildQuboEngines:
    def test_returns_tuple_of_matrix_and_metadata(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        result = build_qubo(mu, sigma, num_assets_to_select=k)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_matrix_shape_is_correct(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, meta = build_qubo(mu, sigma, num_assets_to_select=k)
        assert Q.shape == (4, 4)

    def test_metadata_has_correct_n_and_k(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, meta = build_qubo(mu, sigma, num_assets_to_select=k)
        assert meta.n == 4
        assert meta.k == 2

    def test_metadata_frobenius_norm_is_positive(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, meta = build_qubo(mu, sigma, num_assets_to_select=k)
        assert meta.frobenius_norm > 0.0

    def test_metadata_to_dict_is_json_safe(self):
        import json
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, meta = build_qubo(mu, sigma, num_assets_to_select=k)
        d = meta.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        assert len(json_str) > 0

    def test_metadata_lambda_values_match_input(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, meta = build_qubo(
            mu, sigma, k,
            lambda_return=2.0,
            lambda_risk=3.0,
            lambda_cardinality=10.0,
        )
        assert meta.lambda_return == 2.0
        assert meta.lambda_risk == 3.0
        assert meta.lambda_cardinality == 10.0


# ---------------------------------------------------------------------------
# evaluate_solution (engines layer wrapper)
# ---------------------------------------------------------------------------

class TestEvaluateSolution:
    def test_evaluate_solution_matches_qubo_energy(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        x = np.array([1.0, 0.0, 1.0, 0.0])
        assert evaluate_solution(Q, x) == qubo_energy(Q, x)


# ---------------------------------------------------------------------------
# find_best_bitstring
# ---------------------------------------------------------------------------

class TestFindBestBitstring:
    def test_returns_tuple_of_array_and_float(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        samples = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [1, 1, 0, 0],
        ], dtype=float)
        best_x, best_energy = find_best_bitstring(Q, samples)
        assert isinstance(best_x, np.ndarray)
        assert isinstance(best_energy, float)

    def test_best_energy_is_minimum(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        samples = np.array([
            [1, 0, 1, 0],
            [0, 1, 0, 1],
            [1, 1, 0, 0],
        ], dtype=float)
        best_x, best_energy = find_best_bitstring(Q, samples)
        # Verify it's actually the minimum
        for sample in samples:
            energy = float(sample @ Q @ sample)
            assert best_energy <= energy + 1e-10


# ---------------------------------------------------------------------------
# enumerate_all_solutions
# ---------------------------------------------------------------------------

class TestEnumerateAllSolutions:
    def test_returns_list_of_tuples(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=k)
        assert isinstance(solutions, list)
        for item in solutions:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_correct_number_of_solutions(self):
        """C(4, 2) = 6 solutions for n=4, k=2."""
        from math import comb
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=k)
        assert len(solutions) == comb(4, 2)

    def test_solutions_sorted_by_energy_ascending(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=k)
        energies = [e for _, e in solutions]
        assert energies == sorted(energies)

    def test_each_solution_has_exactly_k_ones(self):
        mu, sigma, k = _make_simple_inputs(n=4, k=2)
        Q, _ = build_qubo(mu, sigma, k)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=k)
        for x, _ in solutions:
            assert int(x.sum()) == k

    def test_too_large_n_raises_value_error(self):
        Q = np.eye(25)  # n=25 > 20
        with pytest.raises(ValueError, match="Brute-force"):
            enumerate_all_solutions(Q, num_assets_to_select=2)


# ---------------------------------------------------------------------------
# compute_approximation_ratio
# ---------------------------------------------------------------------------

class TestComputeApproximationRatio:
    def test_perfect_solution_gives_ratio_one(self):
        """When quantum energy equals optimal energy, ratio = 1.0."""
        result = compute_approximation_ratio(
            quantum_energy=-5.0,
            optimal_energy=-5.0,
        )
        assert result == 1.0

    def test_worse_solution_gives_ratio_greater_than_one(self):
        """Quantum energy worse (less negative) than optimal → ratio > 1.
        
        The ratio is optimal_energy / quantum_energy. When quantum_energy=-3
        and optimal_energy=-5: ratio = -5/-3 = 1.67 > 1.
        A ratio > 1 means the quantum solution is worse than optimal.
        """
        result = compute_approximation_ratio(
            quantum_energy=-3.0,
            optimal_energy=-5.0,
        )
        assert result is not None
        assert result > 1.0

    def test_zero_optimal_energy_returns_none(self):
        result = compute_approximation_ratio(
            quantum_energy=-3.0,
            optimal_energy=0.0,
        )
        assert result is None

    def test_positive_optimal_energy_returns_none(self):
        result = compute_approximation_ratio(
            quantum_energy=2.0,
            optimal_energy=1.0,
        )
        assert result is None

    def test_non_negative_quantum_energy_returns_zero(self):
        result = compute_approximation_ratio(
            quantum_energy=0.0,
            optimal_energy=-5.0,
        )
        assert result == 0.0
