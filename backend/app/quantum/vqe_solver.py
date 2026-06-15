"""VQE-style portfolio optimizer using PennyLane.

Implements a variational quantum eigensolver approach for asset selection
using PennyLane's ``default.qubit`` simulator. The cost Hamiltonian encodes
the QUBO objective; a parameterised ansatz circuit is optimised via
gradient descent to find the minimum energy state.

Algorithm overview
------------------
1. Convert the QUBO matrix to an Ising Hamiltonian via the substitution
   ``x_i = (1 - Z_i) / 2``.
2. Build a hardware-efficient ansatz: alternating Ry rotation layers and
   CNOT entanglement layers.
3. Optimise the ansatz parameters using PennyLane's gradient descent.
4. Sample the optimised circuit multiple times and select the bitstring
   with the lowest QUBO energy.
5. Enforce the cardinality constraint and compute portfolio metrics.

Fallback strategy
-----------------
If PennyLane is not installed, the solver falls back to the same greedy
selection strategy used by the QAOA solver. This ensures graceful
degradation in lightweight environments.

QUBO → Ising transformation
----------------------------
The substitution ``x_i = (1 - Z_i) / 2`` maps binary variables to
Pauli-Z operators::

    x_i x_j = (1 - Z_i)(1 - Z_j) / 4
             = (1 - Z_i - Z_j + Z_i Z_j) / 4

This gives the Ising Hamiltonian::

    H = Σ_i h_i Z_i + Σ_{i<j} J_ij Z_i Z_j + constant

where the constant is dropped (it doesn't affect the optimisation).

Usage::

    from app.quantum.vqe_solver import run_vqe

    result = run_vqe(
        tickers=["AAPL", "MSFT", "GOOGL"],
        qubo_matrix=Q,
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        num_assets_to_select=2,
        num_layers=2,
        max_iterations=100,
    )
    print(result.selected_assets)
    print(result.metrics.sharpe_ratio)
"""

from __future__ import annotations

import time

import numpy as np

from app.core.config import get_settings
from app.core.exceptions import QuantumTimeoutError
from app.core.logging import get_logger
from app.quantum.qaoa_solver import _enforce_cardinality, _greedy_selection
from app.schemas.responses import AssetWeight, PortfolioMetrics, VQEResult


logger = get_logger(__name__)

# Number of samples to draw from the optimised circuit when extracting
# the binary solution. More samples → better chance of finding the
# minimum-energy bitstring.
_NUM_SAMPLES = 50


def run_vqe(
    tickers: list[str],
    qubo_matrix: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    num_assets_to_select: int,
    num_layers: int = 2,
    max_iterations: int = 100,
) -> VQEResult:
    """Run VQE-style optimization using PennyLane to solve the asset selection QUBO.

    Constructs a parameterised quantum circuit (hardware-efficient ansatz),
    optimises its parameters to minimise the Ising Hamiltonian derived from
    the QUBO, then samples the circuit to extract a binary asset selection.

    Args:
        tickers: Asset ticker symbols, length n.
        qubo_matrix: QUBO matrix Q, shape (n, n). Upper-triangular form
            as returned by :func:`~app.quantum.qubo.build_qubo_matrix`.
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD. Used to compute dollar
            allocations in the result.
        num_assets_to_select: Target number of assets k to select.
        num_layers: Number of variational ansatz layers. Each layer
            consists of Ry rotations on all qubits followed by a CNOT
            entanglement chain. Defaults to 2.
        max_iterations: Maximum number of gradient descent steps.
            Defaults to 100. Increase for better solution quality at
            the cost of longer runtime.

    Returns:
        :class:`~app.schemas.responses.VQEResult` containing:
        - ``selected_assets``: List of selected ticker symbols.
        - ``weights``: Equal-weight allocations for selected assets.
        - ``metrics``: Portfolio performance metrics.
        - ``num_qubits``: Number of qubits used (= number of assets).
        - ``solve_time_ms``: Wall-clock time for the solve in milliseconds.

    Raises:
        QuantumTimeoutError: If the solver exceeds the configured
            ``QUANTUM_TIMEOUT_SECONDS`` setting.

    Note:
        The returned portfolio uses **equal weighting** among selected
        assets. This is intentional — the QUBO formulation solves the
        binary asset *selection* problem; continuous weight optimisation
        is handled by the classical Markowitz engine.
    """
    settings = get_settings()
    n = len(tickers)
    start_time = time.perf_counter()

    logger.info(
        "vqe_started",
        num_qubits=n,
        num_layers=num_layers,
        max_iterations=max_iterations,
    )

    x_opt: np.ndarray | None = None

    try:
        # ── Import PennyLane (lazy to allow graceful fallback) ────────────────
        import pennylane as qml  # noqa: PLC0415
        from pennylane import numpy as pnp  # noqa: PLC0415

        dev = qml.device("default.qubit", wires=n)

        # ── Convert QUBO to Ising Hamiltonian ─────────────────────────────────
        h_coeffs, zz_pairs, zz_coeffs = _qubo_to_ising(qubo_matrix)

        # ── Define the cost circuit ───────────────────────────────────────────
        @qml.qnode(dev)
        def cost_circuit(params: np.ndarray) -> float:
            """Hardware-efficient ansatz + cost Hamiltonian expectation value."""
            # Ansatz: alternating Ry rotations and CNOT entanglement
            for layer in range(num_layers):
                for qubit in range(n):
                    qml.RY(params[layer * n + qubit], wires=qubit)
                # Linear entanglement chain: qubit 0 → 1 → 2 → ... → n-1
                for qubit in range(n - 1):
                    qml.CNOT(wires=[qubit, qubit + 1])

            # Build cost Hamiltonian from Ising coefficients
            obs = []
            coeffs = []

            for i, h in enumerate(h_coeffs):
                if abs(h) > 1e-10:
                    obs.append(qml.PauliZ(i))
                    coeffs.append(float(h))

            for (i, j), J in zip(zz_pairs, zz_coeffs):
                if abs(J) > 1e-10:
                    obs.append(qml.PauliZ(i) @ qml.PauliZ(j))
                    coeffs.append(float(J))

            if not obs:
                # Degenerate case: all coefficients are zero
                return qml.expval(qml.Identity(0))

            H = qml.Hamiltonian(coeffs, obs)
            return qml.expval(H)

        # ── Initialise parameters randomly ────────────────────────────────────
        rng = np.random.default_rng(42)
        params = pnp.array(
            rng.uniform(-np.pi, np.pi, num_layers * n),
            requires_grad=True,
        )

        # ── Optimise with gradient descent ────────────────────────────────────
        opt = qml.GradientDescentOptimizer(stepsize=0.1)
        prev_cost = float("inf")

        for step in range(max_iterations):
            # Check timeout at each iteration
            elapsed = time.perf_counter() - start_time
            if elapsed > settings.QUANTUM_TIMEOUT_SECONDS:
                raise QuantumTimeoutError(
                    message=(
                        f"VQE timed out after {step} iterations "
                        f"({elapsed:.1f}s elapsed)."
                    ),
                    timeout_seconds=settings.QUANTUM_TIMEOUT_SECONDS,
                )

            params, cost = opt.step_and_cost(cost_circuit, params)

            # Log progress every 20 steps
            if step % 20 == 0:
                logger.debug(
                    "vqe_iteration",
                    step=step,
                    cost=round(float(cost), 6),
                )

            # Early stopping: convergence check
            if abs(prev_cost - float(cost)) < 1e-6 and step > 10:
                logger.debug("vqe_converged", step=step, cost=round(float(cost), 6))
                break
            prev_cost = float(cost)

        # ── Sample the optimised circuit ──────────────────────────────────────
        @qml.qnode(dev)
        def sample_circuit(params: np.ndarray) -> np.ndarray:
            """Apply the optimised ansatz and sample computational basis states."""
            for layer in range(num_layers):
                for qubit in range(n):
                    qml.RY(params[layer * n + qubit], wires=qubit)
                for qubit in range(n - 1):
                    qml.CNOT(wires=[qubit, qubit + 1])
            return qml.sample(wires=range(n))

        # Take multiple samples and pick the one with lowest QUBO energy
        samples = np.array([sample_circuit(params) for _ in range(_NUM_SAMPLES)])

        # Convert {-1, 1} → {0, 1} if the device returns ±1 eigenvalues
        if samples.min() < 0:
            samples = (samples + 1) // 2

        # Find the sample with the lowest QUBO energy
        best_x = samples[0].astype(float)
        best_energy = float("inf")
        for sample in samples:
            x = sample.astype(float)
            energy = float(x @ qubo_matrix @ x)
            if energy < best_energy:
                best_energy = energy
                best_x = x

        x_opt = best_x

        logger.debug(
            "vqe_best_sample",
            x=x_opt.tolist(),
            energy=round(best_energy, 6),
        )

    except QuantumTimeoutError:
        raise
    except Exception as exc:
        logger.warning(
            "vqe_pennylane_failed_using_greedy_fallback",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        x_opt = _greedy_selection(expected_returns, num_assets_to_select)

    solve_time_ms = (time.perf_counter() - start_time) * 1000

    # ── Enforce cardinality constraint ────────────────────────────────────────
    assert x_opt is not None
    x_binary = _enforce_cardinality(x_opt, num_assets_to_select, expected_returns)
    selected_indices = [i for i in range(n) if x_binary[i] > 0.5]
    selected_tickers = [tickers[i] for i in selected_indices]

    # ── Equal-weight allocation among selected assets ─────────────────────────
    weights_arr = np.zeros(n)
    if selected_indices:
        weight_per_asset = 1.0 / len(selected_indices)
        for i in selected_indices:
            weights_arr[i] = weight_per_asset

    # ── Compute portfolio metrics ─────────────────────────────────────────────
    port_return = float(expected_returns @ weights_arr)
    port_variance = float(weights_arr @ covariance_matrix @ weights_arr)
    port_vol = float(np.sqrt(max(port_variance, 0.0)))
    risk_free = settings.RISK_FREE_RATE
    sharpe = (port_return - risk_free) / port_vol if port_vol > 1e-10 else 0.0

    asset_weights = [
        AssetWeight(
            ticker=tickers[i],
            weight=float(weights_arr[i]),
            allocation=float(weights_arr[i] * budget),
        )
        for i in selected_indices
    ]

    metrics = PortfolioMetrics(
        expected_return=port_return,
        volatility=port_vol,
        sharpe_ratio=sharpe,
        num_assets=len(selected_indices),
    )

    logger.info(
        "vqe_complete",
        selected_tickers=selected_tickers,
        sharpe=round(sharpe, 4),
        expected_return=round(port_return, 4),
        volatility=round(port_vol, 4),
        solve_time_ms=round(solve_time_ms, 1),
    )

    return VQEResult(
        selected_assets=selected_tickers,
        weights=asset_weights,
        metrics=metrics,
        num_qubits=n,
        solve_time_ms=solve_time_ms,
    )


def _qubo_to_ising(
    Q: np.ndarray,
) -> tuple[np.ndarray, list[tuple[int, int]], list[float]]:
    """Convert a QUBO matrix to Ising Hamiltonian coefficients.

    Uses the substitution ``x_i = (1 - Z_i) / 2`` to map binary
    variables to Pauli-Z operators::

        x_i = (1 - Z_i) / 2
        x_i x_j = (1 - Z_i)(1 - Z_j) / 4
                = (1 - Z_i - Z_j + Z_i Z_j) / 4

    The resulting Ising Hamiltonian is::

        H = Σ_i h_i Z_i + Σ_{i<j} J_ij Z_i Z_j + constant

    The constant term is dropped since it doesn't affect the optimisation.

    Args:
        Q: QUBO matrix, shape (n, n). Upper-triangular form.

    Returns:
        Tuple of:
        - ``h_coeffs``: Linear (Z_i) coefficients, shape (n,).
        - ``zz_pairs``: List of (i, j) index pairs for ZZ interactions.
        - ``zz_coeffs``: Corresponding ZZ interaction strengths.

    Example::

        Q = np.array([[1.0, 2.0], [0.0, 3.0]])
        h, pairs, J = _qubo_to_ising(Q)
        # h[0] = -Q[0,0]/2 - Q[0,1]/4 = -0.5 - 0.5 = -1.0
        # h[1] = -Q[1,1]/2 - Q[0,1]/4 = -1.5 - 0.5 = -2.0
        # pairs = [(0, 1)], J = [Q[0,1]/4] = [0.5]
    """
    n = Q.shape[0]
    h_coeffs = np.zeros(n)
    zz_pairs: list[tuple[int, int]] = []
    zz_coeffs: list[float] = []

    for i in range(n):
        # Diagonal term: Q_ii * x_i = Q_ii * (1 - Z_i) / 2
        # Contribution to Z_i coefficient: -Q_ii / 2
        h_coeffs[i] -= Q[i, i] / 2.0

        for j in range(i + 1, n):
            q_ij = Q[i, j]
            if abs(q_ij) < 1e-12:
                continue
            # Off-diagonal: Q_ij * x_i * x_j = Q_ij * (1-Z_i)(1-Z_j) / 4
            # = Q_ij/4 * (1 - Z_i - Z_j + Z_i Z_j)
            # Contributions:
            #   Z_i coefficient: -Q_ij / 4
            #   Z_j coefficient: -Q_ij / 4
            #   Z_i Z_j coefficient: +Q_ij / 4
            h_coeffs[i] -= q_ij / 4.0
            h_coeffs[j] -= q_ij / 4.0
            zz_pairs.append((i, j))
            zz_coeffs.append(q_ij / 4.0)

    return h_coeffs, zz_pairs, zz_coeffs
