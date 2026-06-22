"""Unit tests for app.engines.quantum.qubo — engines-layer QUBO wrapper.

Tests cover:
- build_qubo: returns (Q, QUBOMetadata) tuple with correct shapes
- QUBOMetadata: all fields populated correctly
- evaluate_solution: delegates to qubo_energy correctly
- find_best_bitstring: finds minimum energy sample
- enumerate_all_solutions: brute-force enumeration, sorted by energy
- compute_approximation_ratio: ratio in [0, 1] for valid inputs
- Re-exported functions from app.quantum.qubo are accessible
"""

import numpy as np
import pytest

from app.engines.quantum.qubo import (
    QUBOMetadata,
    build_qubo,
    compute_approximation_ratio,
    decode_bitstring,
    enumerate_all_solutions,
    evaluate_solution,
    find_best_bitstring,
    qubo_energy,
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


# ── build_qubo ────────────────────────────────────────────────────────────────

class TestBuildQubo:
    """Tests for build_qubo (engines-layer wrapper)."""

    def test_returns_tuple_of_matrix_and_metadata(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        result = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_matrix_shape_is_n_by_n(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert Q.shape == (4, 4)

    def test_metadata_is_qubo_metadata_instance(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert isinstance(meta, QUBOMetadata)

    def test_metadata_n_matches_num_assets(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert meta.n == 4

    def test_metadata_k_matches_num_assets_to_select(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=3)
        assert meta.k == 3

    def test_metadata_lambda_values_stored(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(
            mu_4, sigma_4,
            num_assets_to_select=2,
            lambda_return=2.0,
            lambda_risk=1.5,
            lambda_cardinality=7.0,
        )
        assert meta.lambda_return == 2.0
        assert meta.lambda_risk == 1.5
        assert meta.lambda_cardinality == 7.0

    def test_metadata_frobenius_norm_is_positive(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert meta.frobenius_norm > 0.0

    def test_metadata_num_nonzero_is_positive(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert meta.num_nonzero > 0

    def test_metadata_min_val_le_max_val(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert meta.min_val <= meta.max_val

    def test_metadata_ret_scale_is_positive(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert meta.ret_scale > 0.0

    def test_metadata_cov_scale_is_positive(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        assert meta.cov_scale > 0.0

    def test_metadata_to_dict_is_json_safe(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        import json
        Q, meta = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        d = meta.to_dict()
        # Should be JSON-serialisable
        json_str = json.dumps(d)
        assert "n" in json_str
        assert "k" in json_str


# ── evaluate_solution ─────────────────────────────────────────────────────────

class TestEvaluateSolution:
    """Tests for evaluate_solution."""

    def test_delegates_to_qubo_energy(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 1.0, 0.0])
        energy_eval = evaluate_solution(Q, x)
        energy_direct = qubo_energy(Q, x)
        assert abs(energy_eval - energy_direct) < 1e-12

    def test_returns_float(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([1.0, 0.0, 0.0, 1.0])
        assert isinstance(evaluate_solution(Q, x), float)


# ── find_best_bitstring ───────────────────────────────────────────────────────

class TestFindBestBitstring:
    """Tests for find_best_bitstring."""

    def test_returns_tuple_of_array_and_float(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        samples = np.array([
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 0.0, 1.0],
        ])
        best_x, best_energy = find_best_bitstring(Q, samples)
        assert isinstance(best_x, np.ndarray)
        assert isinstance(best_energy, float)

    def test_best_energy_is_minimum(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        samples = np.array([
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0],
            [1.0, 0.0, 0.0, 1.0],
        ])
        best_x, best_energy = find_best_bitstring(Q, samples)
        # Verify it's actually the minimum
        for sample in samples:
            e = float(sample @ Q @ sample)
            assert best_energy <= e + 1e-10

    def test_single_sample_returns_that_sample(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        x = np.array([[1.0, 0.0, 1.0, 0.0]])
        best_x, best_energy = find_best_bitstring(Q, x)
        np.testing.assert_array_equal(best_x, x[0])


# ── enumerate_all_solutions ───────────────────────────────────────────────────

class TestEnumerateAllSolutions:
    """Tests for enumerate_all_solutions."""

    def test_returns_list_of_tuples(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=2)
        assert isinstance(solutions, list)
        assert all(isinstance(s, tuple) and len(s) == 2 for s in solutions)

    def test_correct_number_of_solutions(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """C(4, 2) = 6 solutions for k=2 from 4 assets."""
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=2)
        assert len(solutions) == 6

    def test_solutions_sorted_by_energy_ascending(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=2)
        energies = [e for _, e in solutions]
        assert energies == sorted(energies)

    def test_each_solution_has_exactly_k_ones(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=2)
        for x, _ in solutions:
            assert int(x.sum()) == 2

    def test_too_large_n_raises(self) -> None:
        Q = np.eye(25)
        with pytest.raises(ValueError, match="Brute-force"):
            enumerate_all_solutions(Q, num_assets_to_select=2)

    def test_k_equals_1_gives_n_solutions(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        """C(4, 1) = 4 solutions."""
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=1)
        solutions = enumerate_all_solutions(Q, num_assets_to_select=1)
        assert len(solutions) == 4


# ── compute_approximation_ratio ───────────────────────────────────────────────

class TestComputeApproximationRatio:
    """Tests for compute_approximation_ratio."""

    def test_optimal_solution_gives_ratio_one(self) -> None:
        # quantum_energy == optimal_energy → ratio = 1.0
        ratio = compute_approximation_ratio(
            quantum_energy=-5.0,
            optimal_energy=-5.0,
        )
        assert ratio is not None
        assert abs(ratio - 1.0) < 1e-10

    def test_worse_solution_gives_ratio_greater_than_one(self) -> None:
        # quantum_energy=-3.0 is worse than optimal=-5.0 (less negative)
        # ratio = optimal / quantum = -5.0 / -3.0 = 1.667 (> 1)
        ratio = compute_approximation_ratio(
            quantum_energy=-3.0,
            optimal_energy=-5.0,
        )
        assert ratio is not None
        assert ratio > 1.0

    def test_zero_optimal_energy_returns_none(self) -> None:
        ratio = compute_approximation_ratio(
            quantum_energy=-3.0,
            optimal_energy=0.0,
        )
        assert ratio is None

    def test_positive_optimal_energy_returns_none(self) -> None:
        ratio = compute_approximation_ratio(
            quantum_energy=2.0,
            optimal_energy=1.0,
        )
        assert ratio is None

    def test_positive_quantum_energy_gives_zero_ratio(self) -> None:
        ratio = compute_approximation_ratio(
            quantum_energy=1.0,
            optimal_energy=-5.0,
        )
        assert ratio == 0.0

    def test_ratio_is_float(self) -> None:
        ratio = compute_approximation_ratio(-4.0, -5.0)
        assert isinstance(ratio, float)


# ── Re-exported functions ─────────────────────────────────────────────────────

class TestReExportedFunctions:
    """Tests that re-exported functions from app.quantum.qubo are accessible."""

    def test_decode_bitstring_accessible(self) -> None:
        x = decode_bitstring("101")
        np.testing.assert_array_equal(x, [1.0, 0.0, 1.0])

    def test_validate_qubo_solution_accessible(self) -> None:
        x = np.array([1.0, 0.0, 1.0, 0.0])
        valid, _ = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        assert valid is True

    def test_qubo_energy_accessible(
        self,
        mu_4: np.ndarray,
        sigma_4: np.ndarray,
    ) -> None:
        Q, _ = build_qubo(mu_4, sigma_4, num_assets_to_select=2)
        x = np.zeros(4)
        assert qubo_energy(Q, x) == 0.0
