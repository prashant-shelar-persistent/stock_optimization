"""QUBO (Quadratic Unconstrained Binary Optimization) formulator.

This module is the canonical QUBO implementation for the
``app.engines.quantum`` package. It re-exports and extends the core QUBO
functions from :mod:`app.quantum.qubo` with additional utilities needed
by the engines layer.

Problem formulation
-------------------
Select k assets from n candidates to maximise risk-adjusted return.

QUBO objective (minimisation form)::

    min  -λ_ret * Σ_i μ_i x_i
         + λ_risk * Σ_ij σ_ij x_i x_j
         + λ_card * (Σ_i x_i - k)²

where:
    x_i ∈ {0, 1}  — binary asset selection variable
    μ_i           — expected return of asset i
    σ_ij          — covariance between assets i and j
    k             — target number of assets to select
    λ_ret         — return penalty weight
    λ_risk        — risk penalty weight
    λ_card        — cardinality constraint penalty weight

The QUBO matrix Q is upper-triangular (diagonal holds linear terms,
off-diagonal holds quadratic terms). The objective is x^T Q x.

Normalisation
-------------
Expected returns and covariance values are normalised to the same scale
before building Q to prevent one term from dominating. This improves
the quality of quantum solutions by keeping the energy landscape balanced.

Usage::

    from app.engines.quantum.qubo import (
        build_qubo,
        evaluate_solution,
        decode_bitstring,
        QUBOMetadata,
    )
    import numpy as np

    mu = np.array([0.12, 0.10, 0.09, 0.15])
    sigma = np.eye(4) * 0.04

    qubo, meta = build_qubo(
        expected_returns=mu,
        covariance_matrix=sigma,
        num_assets_to_select=2,
    )

    # Evaluate a candidate solution
    x = np.array([1.0, 0.0, 0.0, 1.0])
    energy = evaluate_solution(qubo, x)
    print(f"QUBO energy: {energy:.4f}")
    print(f"Matrix stats: {meta}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Re-export core QUBO utilities from the lower-level quantum module
# so callers can import from one place.
from app.quantum.qubo import (  # noqa: F401
    build_qubo_matrix,
    decode_bitstring,
    qubo_energy,
    qubo_to_dict,
    validate_qubo_solution,
)


@dataclass
class QUBOMetadata:
    """Metadata about a built QUBO matrix.

    Attributes:
        n: Number of assets (= number of qubits).
        k: Target number of assets to select.
        lambda_return: Return maximisation weight used.
        lambda_risk: Risk minimisation weight used.
        lambda_cardinality: Cardinality penalty weight used.
        min_val: Minimum value in the QUBO matrix.
        max_val: Maximum value in the QUBO matrix.
        frobenius_norm: Frobenius norm of the QUBO matrix.
        num_nonzero: Number of non-zero entries in the QUBO matrix.
        ret_scale: Normalisation scale applied to expected returns.
        cov_scale: Normalisation scale applied to covariance values.
        extra: Additional metadata.
    """

    n: int
    k: int
    lambda_return: float
    lambda_risk: float
    lambda_cardinality: float
    min_val: float
    max_val: float
    frobenius_norm: float
    num_nonzero: int
    ret_scale: float
    cov_scale: float
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "n": self.n,
            "k": self.k,
            "lambda_return": self.lambda_return,
            "lambda_risk": self.lambda_risk,
            "lambda_cardinality": self.lambda_cardinality,
            "min_val": round(self.min_val, 6),
            "max_val": round(self.max_val, 6),
            "frobenius_norm": round(self.frobenius_norm, 4),
            "num_nonzero": self.num_nonzero,
            "ret_scale": round(self.ret_scale, 8),
            "cov_scale": round(self.cov_scale, 8),
            **self.extra,
        }


def build_qubo(
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    num_assets_to_select: int,
    lambda_return: float = 1.0,
    lambda_risk: float = 1.0,
    lambda_cardinality: float = 5.0,
) -> tuple[np.ndarray, QUBOMetadata]:
    """Build the QUBO matrix and return it with rich metadata.

    This is the primary entry point for the engines layer. It wraps
    :func:`~app.quantum.qubo.build_qubo_matrix` and computes additional
    statistics about the resulting matrix.

    Args:
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
            Must be symmetric and positive semi-definite.
        num_assets_to_select: Target number of assets k (1 ≤ k ≤ n).
        lambda_return: Weight for the return maximisation term.
            Higher values push the solver toward high-return assets.
            Defaults to 1.0.
        lambda_risk: Weight for the risk minimisation term.
            Higher values push the solver toward low-correlation assets.
            Defaults to 1.0.
        lambda_cardinality: Penalty weight for the cardinality constraint.
            Must be large enough to dominate the objective (≥ 5 * max(|Q|)
            is a safe heuristic). Defaults to 5.0.

    Returns:
        Tuple of:
        - ``Q``: QUBO matrix of shape (n, n) in upper-triangular form.
        - ``metadata``: :class:`QUBOMetadata` with matrix statistics.

    Raises:
        ValueError: If inputs have incompatible shapes or k is out of range.

    Example::

        mu = np.array([0.12, 0.10, 0.09])
        sigma = np.array([[0.04, 0.01, 0.01],
                          [0.01, 0.03, 0.01],
                          [0.01, 0.01, 0.05]])
        Q, meta = build_qubo(mu, sigma, num_assets_to_select=2)
        # Q.shape == (3, 3)
        # meta.n == 3, meta.k == 2
    """
    expected_returns = np.asarray(expected_returns, dtype=float)
    covariance_matrix = np.asarray(covariance_matrix, dtype=float)
    n = len(expected_returns)

    # Compute normalisation scales (same as in build_qubo_matrix)
    ret_scale = float(np.max(np.abs(expected_returns)) + 1e-8)
    cov_scale = float(np.max(np.abs(covariance_matrix)) + 1e-8)

    # Build the QUBO matrix using the core implementation
    Q = build_qubo_matrix(
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        num_assets_to_select=num_assets_to_select,
        lambda_return=lambda_return,
        lambda_risk=lambda_risk,
        lambda_cardinality=lambda_cardinality,
    )

    # Compute matrix statistics for metadata
    num_nonzero = int(np.count_nonzero(np.abs(Q) > 1e-12))
    frobenius_norm = float(np.linalg.norm(Q, "fro"))
    min_val = float(Q.min())
    max_val = float(Q.max())

    metadata = QUBOMetadata(
        n=n,
        k=num_assets_to_select,
        lambda_return=lambda_return,
        lambda_risk=lambda_risk,
        lambda_cardinality=lambda_cardinality,
        min_val=min_val,
        max_val=max_val,
        frobenius_norm=frobenius_norm,
        num_nonzero=num_nonzero,
        ret_scale=ret_scale,
        cov_scale=cov_scale,
    )

    return Q, metadata


def evaluate_solution(
    qubo_matrix: np.ndarray,
    x: np.ndarray,
) -> float:
    """Compute the QUBO objective value for a binary solution vector.

    Evaluates the quadratic form ``x^T Q x`` where Q is the QUBO matrix
    and x is a binary solution vector.

    Args:
        qubo_matrix: QUBO matrix, shape (n, n). Upper-triangular form as
            returned by :func:`build_qubo`.
        x: Binary solution vector, shape (n,). Values should be 0 or 1.

    Returns:
        Scalar QUBO energy (lower is better for minimisation problems).

    Example::

        Q, _ = build_qubo(mu, sigma, k=2)
        x = np.array([1.0, 0.0, 1.0])
        energy = evaluate_solution(Q, x)
    """
    return qubo_energy(qubo_matrix, x)


def find_best_bitstring(
    qubo_matrix: np.ndarray,
    samples: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Find the sample with the lowest QUBO energy.

    Given a set of binary samples (e.g. from quantum circuit measurements),
    returns the one that minimises the QUBO objective.

    Args:
        qubo_matrix: QUBO matrix, shape (n, n).
        samples: Binary sample matrix, shape (num_samples, n).
            Each row is a binary vector.

    Returns:
        Tuple of:
        - ``best_x``: Binary vector with the lowest QUBO energy, shape (n,).
        - ``best_energy``: The corresponding QUBO energy value.

    Example::

        Q, _ = build_qubo(mu, sigma, k=2)
        samples = np.array([[1, 0, 1], [0, 1, 1], [1, 1, 0]])
        best_x, best_energy = find_best_bitstring(Q, samples)
    """
    best_x = samples[0].astype(float)
    best_energy = float("inf")

    for sample in samples:
        x = sample.astype(float)
        energy = float(x @ qubo_matrix @ x)
        if energy < best_energy:
            best_energy = energy
            best_x = x.copy()

    return best_x, best_energy


def enumerate_all_solutions(
    qubo_matrix: np.ndarray,
    num_assets_to_select: int,
) -> list[tuple[np.ndarray, float]]:
    """Enumerate all feasible solutions and their QUBO energies.

    Brute-force enumeration of all binary vectors with exactly k ones.
    Only feasible for small n (≤ 12 assets). Used for validation and
    benchmarking quantum solver quality.

    Args:
        qubo_matrix: QUBO matrix, shape (n, n).
        num_assets_to_select: Target number of assets k.

    Returns:
        List of (x, energy) tuples sorted by energy ascending.
        Each x is a binary vector with exactly k ones.

    Raises:
        ValueError: If n > 20 (too large for brute force).

    Example::

        Q, _ = build_qubo(mu, sigma, k=2)
        solutions = enumerate_all_solutions(Q, k=2)
        optimal_x, optimal_energy = solutions[0]
    """
    from itertools import combinations  # noqa: PLC0415

    n = qubo_matrix.shape[0]
    if n > 20:
        raise ValueError(
            f"Brute-force enumeration is only feasible for n ≤ 20, got n={n}. "
            "Use the quantum solver for larger problems."
        )

    k = num_assets_to_select
    results: list[tuple[np.ndarray, float]] = []

    for indices in combinations(range(n), k):
        x = np.zeros(n)
        x[list(indices)] = 1.0
        energy = float(x @ qubo_matrix @ x)
        results.append((x, energy))

    results.sort(key=lambda t: t[1])
    return results


def compute_approximation_ratio(
    quantum_energy: float,
    optimal_energy: float,
) -> float | None:
    """Compute the approximation ratio of a quantum solution vs. the optimal.

    The approximation ratio measures how close the quantum solution is to
    the classical optimum. A ratio of 1.0 means the quantum solver found
    the optimal solution.

    Args:
        quantum_energy: QUBO energy of the quantum solution.
        optimal_energy: QUBO energy of the optimal (brute-force) solution.

    Returns:
        Approximation ratio in [0, 1] if optimal_energy < 0 (typical for
        well-formulated QUBOs), or ``None`` if the ratio cannot be computed
        (e.g. optimal_energy is zero or positive).

    Note:
        For minimisation problems with negative optimal energy, the ratio
        is defined as ``optimal_energy / quantum_energy`` (both negative,
        so the ratio is in (0, 1]).
    """
    if abs(optimal_energy) < 1e-10:
        return None
    if optimal_energy > 0:
        # Unusual case: positive optimal energy
        return None
    if quantum_energy >= 0:
        return 0.0
    return float(optimal_energy / quantum_energy)
