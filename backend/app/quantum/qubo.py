"""QUBO (Quadratic Unconstrained Binary Optimization) formulator.

Converts the asset selection problem into a QUBO matrix suitable for
QAOA (Qiskit) and VQE-style (PennyLane) quantum optimizers.

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

    from app.quantum.qubo import build_qubo_matrix, qubo_energy, decode_bitstring
    import numpy as np

    mu = np.array([0.12, 0.10, 0.09, 0.15])
    sigma = np.eye(4) * 0.04
    Q = build_qubo_matrix(mu, sigma, num_assets_to_select=2)

    # Evaluate a candidate solution
    x = np.array([1.0, 0.0, 0.0, 1.0])
    energy = qubo_energy(Q, x)

    # Decode a bitstring from a quantum measurement
    x2 = decode_bitstring("1001")
"""

from __future__ import annotations

import numpy as np


def build_qubo_matrix(
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    num_assets_to_select: int,
    lambda_return: float = 1.0,
    lambda_risk: float = 1.0,
    lambda_cardinality: float = 5.0,
) -> np.ndarray:
    """Build the QUBO matrix for asset selection.

    Constructs the upper-triangular QUBO matrix Q such that the
    optimisation objective is ``min x^T Q x`` over binary vectors x.

    The three terms are:

    1. **Return maximisation** (diagonal): ``-λ_ret * μ_i`` per asset.
    2. **Risk minimisation** (diagonal + off-diagonal): ``λ_risk * σ_ij``.
    3. **Cardinality constraint** (penalty): ``λ_card * (Σ x_i - k)²``.

    Args:
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
            Must be symmetric and positive semi-definite.
        num_assets_to_select: Target number of assets k (1 ≤ k ≤ n).
        lambda_return: Weight for the return maximisation term.
            Higher values push the solver toward high-return assets.
        lambda_risk: Weight for the risk minimisation term.
            Higher values push the solver toward low-correlation assets.
        lambda_cardinality: Penalty weight for the cardinality constraint.
            Must be large enough to dominate the objective (≥ 5 * max(|Q|)
            is a safe heuristic). Defaults to 5.0.

    Returns:
        QUBO matrix Q of shape (n, n) in upper-triangular form.
        Diagonal entries hold linear (single-variable) terms.
        Off-diagonal entries Q[i, j] (i < j) hold quadratic terms.

    Raises:
        ValueError: If inputs have incompatible shapes or k is out of range.

    Example::

        mu = np.array([0.12, 0.10, 0.09])
        sigma = np.array([[0.04, 0.01, 0.01],
                          [0.01, 0.03, 0.01],
                          [0.01, 0.01, 0.05]])
        Q = build_qubo_matrix(mu, sigma, num_assets_to_select=2)
        # Q.shape == (3, 3)
    """
    expected_returns = np.asarray(expected_returns, dtype=float)
    covariance_matrix = np.asarray(covariance_matrix, dtype=float)

    n = len(expected_returns)

    if covariance_matrix.shape != (n, n):
        raise ValueError(
            f"covariance_matrix must be ({n}, {n}), "
            f"got {covariance_matrix.shape}"
        )
    if not (1 <= num_assets_to_select <= n):
        raise ValueError(
            f"num_assets_to_select must be in [1, {n}], "
            f"got {num_assets_to_select}"
        )

    # ── Normalise to similar scales ──────────────────────────────────────────
    # This prevents the cardinality penalty from being swamped by large
    # covariance values or vice versa.
    ret_scale = np.max(np.abs(expected_returns)) + 1e-8
    cov_scale = np.max(np.abs(covariance_matrix)) + 1e-8

    mu_norm = expected_returns / ret_scale
    sigma_norm = covariance_matrix / cov_scale

    Q = np.zeros((n, n))

    # ── Term 1: Return maximisation (diagonal) ───────────────────────────────
    # Minimising -λ_ret * μ_i x_i  →  Q_ii -= λ_ret * μ_i
    for i in range(n):
        Q[i, i] -= lambda_return * mu_norm[i]

    # ── Term 2: Risk minimisation (diagonal + upper triangle) ────────────────
    # Minimising λ_risk * Σ_ij σ_ij x_i x_j
    # For i == j: σ_ii x_i² = σ_ii x_i  (since x_i² = x_i for binary)
    # For i < j:  combine x_i x_j and x_j x_i into upper triangle
    for i in range(n):
        Q[i, i] += lambda_risk * sigma_norm[i, i]
        for j in range(i + 1, n):
            # Upper triangular: 2 * σ_ij because x_i x_j appears twice
            Q[i, j] += lambda_risk * 2.0 * sigma_norm[i, j]

    # ── Term 3: Cardinality constraint penalty ───────────────────────────────
    # Expanding (Σ x_i - k)² = Σ_i x_i² - 2k Σ_i x_i + k²
    # Since x_i² = x_i for binary:
    #   diagonal contribution: (1 - 2k) * λ_card
    #   off-diagonal contribution: 2 * λ_card  (for each pair i < j)
    k = num_assets_to_select
    for i in range(n):
        Q[i, i] += lambda_cardinality * (1 - 2 * k)
        for j in range(i + 1, n):
            Q[i, j] += lambda_cardinality * 2.0

    return Q


def qubo_energy(Q: np.ndarray, x: np.ndarray) -> float:
    """Compute the QUBO objective value for a binary solution vector.

    Evaluates the quadratic form ``x^T Q x`` where Q is the QUBO matrix
    and x is a binary solution vector.

    Args:
        Q: QUBO matrix, shape (n, n). Upper-triangular form as returned
            by :func:`build_qubo_matrix`.
        x: Binary solution vector, shape (n,). Values should be 0 or 1.

    Returns:
        Scalar QUBO energy (lower is better for minimisation problems).

    Example::

        Q = build_qubo_matrix(mu, sigma, k=2)
        x = np.array([1.0, 0.0, 1.0])
        energy = qubo_energy(Q, x)
    """
    x = np.asarray(x, dtype=float)
    return float(x @ Q @ x)


def decode_bitstring(bitstring: str) -> np.ndarray:
    """Convert a bitstring (e.g. '10110') to a binary numpy array.

    Quantum measurement results are typically returned as bitstrings.
    This function converts them to numpy arrays for use with
    :func:`qubo_energy` and the portfolio weight computation.

    Args:
        bitstring: String of '0' and '1' characters. Whitespace is stripped.
            May be in big-endian (leftmost = qubit 0) or little-endian
            format depending on the quantum framework — the caller is
            responsible for any necessary reversal.

    Returns:
        Binary numpy array of shape (len(bitstring),) with dtype float64.

    Raises:
        ValueError: If the bitstring contains characters other than '0' and '1'.

    Example::

        x = decode_bitstring("10110")
        # x == np.array([1., 0., 1., 1., 0.])
    """
    bitstring = bitstring.strip()
    if not all(c in "01" for c in bitstring):
        raise ValueError(
            f"bitstring must contain only '0' and '1', got: {bitstring!r}"
        )
    return np.array([int(b) for b in bitstring], dtype=float)


def validate_qubo_solution(
    x: np.ndarray,
    num_assets_to_select: int,
    n: int,
) -> tuple[bool, str]:
    """Validate that a QUBO solution satisfies the cardinality constraint.

    Args:
        x: Binary solution vector, shape (n,).
        num_assets_to_select: Expected number of selected assets k.
        n: Total number of assets.

    Returns:
        Tuple of (is_valid, message). ``is_valid`` is True if exactly k
        assets are selected. ``message`` describes any violation.

    Example::

        x = np.array([1., 0., 1., 0.])
        valid, msg = validate_qubo_solution(x, num_assets_to_select=2, n=4)
        # valid == True
    """
    x_binary = np.asarray(x, dtype=float)
    selected = int(np.round(x_binary).sum())

    if selected == num_assets_to_select:
        return True, f"Valid: {selected} assets selected."

    return False, (
        f"Cardinality violation: expected {num_assets_to_select} assets, "
        f"got {selected} selected out of {n}."
    )


def qubo_to_dict(
    Q: np.ndarray,
    tickers: list[str],
) -> dict[tuple[str, str], float]:
    """Convert a QUBO matrix to a dictionary of (ticker_i, ticker_j) → coefficient.

    This format is compatible with D-Wave's dimod library and other
    QUBO-based solvers that accept dictionary representations.

    Args:
        Q: QUBO matrix, shape (n, n). Upper-triangular form.
        tickers: Ticker symbols corresponding to each row/column.

    Returns:
        Dictionary mapping (ticker_i, ticker_j) pairs to QUBO coefficients.
        Only non-zero entries are included. Diagonal entries use
        (ticker_i, ticker_i) keys (linear terms).

    Example::

        Q = build_qubo_matrix(mu, sigma, k=2)
        d = qubo_to_dict(Q, ["AAPL", "MSFT", "GOOGL"])
        # {("AAPL", "AAPL"): -0.5, ("AAPL", "MSFT"): 0.3, ...}
    """
    n = Q.shape[0]
    result: dict[tuple[str, str], float] = {}

    for i in range(n):
        for j in range(i, n):
            val = float(Q[i, j])
            if abs(val) > 1e-12:
                result[(tickers[i], tickers[j])] = val

    return result
