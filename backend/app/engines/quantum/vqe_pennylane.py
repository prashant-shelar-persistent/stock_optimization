"""VQE-style portfolio optimizer using PennyLane.

Implements :class:`VQESolver`, a concrete :class:`~app.engines.quantum.base.BaseQuantumSolver`
that uses a variational quantum eigensolver approach for asset selection
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

    from app.engines.quantum.vqe_pennylane import VQESolver

    solver = VQESolver()
    result = solver.solve(
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

import time
from typing import Any

import numpy as np

from app.core.exceptions import QuantumTimeoutError
from app.core.logging import get_logger
from app.engines.quantum.base import BaseQuantumSolver
from app.engines.quantum.schemas import QuantumAssetResult


logger = get_logger(__name__)

# Number of samples to draw from the optimised circuit when extracting
# the binary solution. More samples → better chance of finding the
# minimum-energy bitstring.
_NUM_SAMPLES = 50


class VQESolver(BaseQuantumSolver):
    """VQE-style portfolio optimizer backed by PennyLane.

    Uses PennyLane's ``default.qubit`` simulator with a hardware-efficient
    ansatz (Ry rotations + CNOT entanglement) and gradient descent
    optimisation to minimise the Ising Hamiltonian derived from the QUBO.

    Attributes:
        settings: Application settings (used for timeout and risk-free rate).
    """

    def __init__(self) -> "None":
        """Initialise the VQE solver."""
        from app.core.config import get_settings as _get_settings  # noqa: PLC0415
        self.settings = _get_settings()

    @property
    def name(self) -> str:
        """Algorithm name."""
        return "VQE"

    def solve(
        self,
        tickers: list[str],
        qubo_matrix: np.ndarray,
        expected_returns: np.ndarray,
        covariance_matrix: np.ndarray,
        budget: float,
        num_assets_to_select: int,
        sector_tags: dict[str, str] | None = None,
        num_layers: int = 2,
        max_iterations: int = 100,
        **kwargs: Any,
    ) -> "QuantumAssetResult":
        """Run VQE-style optimization using PennyLane to solve the asset selection QUBO.

        Constructs a parameterised quantum circuit (hardware-efficient ansatz),
        optimises its parameters to minimise the Ising Hamiltonian derived from
        the QUBO, then samples the circuit to extract a binary asset selection.

        Args:
            tickers: Asset ticker symbols, length n.
            qubo_matrix: QUBO matrix Q, shape (n, n). Upper-triangular form
                as returned by :func:`~app.engines.quantum.qubo.build_qubo`.
            expected_returns: Annualised expected returns, shape (n,).
            covariance_matrix: Annualised covariance matrix, shape (n, n).
            budget: Total investment budget in USD.
            num_assets_to_select: Target number of assets k to select.
            sector_tags: Optional mapping of ticker → GICS sector name.
            num_layers: Number of variational ansatz layers. Each layer
                consists of Ry rotations on all qubits followed by a CNOT
                entanglement chain. Defaults to 2.
            max_iterations: Maximum number of gradient descent steps.
                Defaults to 100. Increase for better solution quality at
                the cost of longer runtime.
            **kwargs: Additional keyword arguments (ignored).

        Returns:
            :class:`~app.engines.quantum.schemas.QuantumAssetResult` containing:
            - ``selected_assets``: List of selected ticker symbols.
            - ``weights``: Equal-weight allocations for selected assets.
            - ``metrics``: Portfolio performance metrics.
            - ``num_qubits``: Number of qubits used (= number of assets).
            - ``solve_time_ms``: Wall-clock time for the solve in milliseconds.
            - ``fallback_used``: True if greedy fallback was used.

        Raises:
            QuantumTimeoutError: If the solver exceeds the configured
                ``QUANTUM_TIMEOUT_SECONDS`` setting.

        Note:
            The returned portfolio uses **equal weighting** among selected
            assets. This is intentional — the QUBO formulation solves the
            binary asset *selection* problem; continuous weight optimisation
            is handled by the classical Markowitz engine.
        """
        n = len(tickers)
        start_time = time.perf_counter()
        fallback_used = False

        logger.info(
            "vqe_started",
            num_qubits=n,
            num_layers=num_layers,
            max_iterations=max_iterations,
        )

        x_opt: np.ndarray | None = None

        try:
            # ── Import PennyLane (lazy to allow graceful fallback) ────────────
            import pennylane as qml  # noqa: PLC0415
            from pennylane import numpy as pnp  # noqa: PLC0415

            dev = qml.device("default.qubit", wires=n)

            # ── Convert QUBO to Ising Hamiltonian ─────────────────────────────
            h_coeffs, zz_pairs, zz_coeffs = _qubo_to_ising(qubo_matrix)

            # ── Define the cost circuit ───────────────────────────────────────
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

            # ── Initialise parameters randomly ────────────────────────────────
            rng = np.random.default_rng(42)
            params = pnp.array(
                rng.uniform(-np.pi, np.pi, num_layers * n),
                requires_grad=True,
            )

            # ── Optimise with gradient descent ────────────────────────────────
            opt = qml.GradientDescentOptimizer(stepsize=0.1)
            prev_cost = float("inf")

            for step in range(max_iterations):
                # Check timeout at each iteration
                elapsed = time.perf_counter() - start_time
                if elapsed > self.settings.QUANTUM_TIMEOUT_SECONDS:
                    raise QuantumTimeoutError(
                        message=(
                            f"VQE timed out after {step} iterations "
                            f"({elapsed:.1f}s elapsed)."
                        ),
                        timeout_seconds=self.settings.QUANTUM_TIMEOUT_SECONDS,
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
                    logger.debug(
                        "vqe_converged",
                        step=step,
                        cost=round(float(cost), 6),
                    )
                    break
                prev_cost = float(cost)

            # ── Sample the optimised circuit ──────────────────────────────────
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
                    best_x = x.copy()

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
            x_opt = self._greedy_selection(expected_returns, num_assets_to_select)
            fallback_used = True

        solve_time_ms = (time.perf_counter() - start_time) * 1000.0

        # ── Enforce cardinality constraint ────────────────────────────────────
        assert x_opt is not None
        x_binary = self._enforce_cardinality(
            x_opt, num_assets_to_select, expected_returns
        )
        selected_indices = [i for i in range(n) if x_binary[i] > 0.5]
        selected_tickers = [tickers[i] for i in selected_indices]

        # ── Build equal-weight portfolio ──────────────────────────────────────
        weights_list, metrics = self._build_equal_weight_portfolio(
            tickers=tickers,
            x_binary=x_binary,
            expected_returns=expected_returns,
            covariance_matrix=covariance_matrix,
            budget=budget,
            sector_tags=sector_tags,
            risk_free_rate=self.settings.RISK_FREE_RATE,
        )

        # Compute QUBO energy for the selected solution
        qubo_energy_val = float(x_binary @ qubo_matrix @ x_binary)
        metrics.qubo_energy = qubo_energy_val

        logger.info(
            "vqe_complete",
            selected_tickers=selected_tickers,
            sharpe=round(metrics.sharpe_ratio, 4),
            expected_return=round(metrics.expected_return, 4),
            volatility=round(metrics.volatility, 4),
            solve_time_ms=round(solve_time_ms, 1),
            fallback_used=fallback_used,
        )

        return QuantumAssetResult(
            algorithm="VQE",
            selected_assets=selected_tickers,
            weights=weights_list,
            metrics=metrics,
            solve_time_ms=solve_time_ms,
            num_qubits=n,
            circuit_depth=num_layers * n,  # Approximate: layers × qubits
            solver_used=(
                "pennylane_default.qubit" if not fallback_used else "greedy_fallback"
            ),
            fallback_used=fallback_used,
            extra={
                "num_layers": num_layers,
                "max_iterations": max_iterations,
                "qubo_energy": round(qubo_energy_val, 6),
                "num_assets_to_select": num_assets_to_select,
            },
        )


def run_vqe(
    tickers: list[str],
    qubo_matrix: np.ndarray,
    expected_returns: np.ndarray,
    covariance_matrix: np.ndarray,
    budget: float,
    num_assets_to_select: int,
    sector_tags: dict[str, str] | None = None,
    num_layers: int = 2,
    max_iterations: int = 100,
) -> "QuantumAssetResult":
    """Convenience function to run VQE without instantiating the solver class.

    Creates a :class:`VQESolver` instance and calls :meth:`~VQESolver.solve`.

    Args:
        tickers: Asset ticker symbols, length n.
        qubo_matrix: QUBO matrix Q, shape (n, n).
        expected_returns: Annualised expected returns, shape (n,).
        covariance_matrix: Annualised covariance matrix, shape (n, n).
        budget: Total investment budget in USD.
        num_assets_to_select: Target number of assets k to select.
        sector_tags: Optional mapping of ticker → GICS sector name.
        num_layers: Number of VQE ansatz layers. Defaults to 2.
        max_iterations: Maximum gradient descent steps. Defaults to 100.

    Returns:
        :class:`~app.engines.quantum.schemas.QuantumAssetResult`.

    Raises:
        QuantumTimeoutError: If the solver exceeds the configured timeout.
    """
    solver = VQESolver()
    return solver.solve(
        tickers=tickers,
        qubo_matrix=qubo_matrix,
        expected_returns=expected_returns,
        covariance_matrix=covariance_matrix,
        budget=budget,
        num_assets_to_select=num_assets_to_select,
        sector_tags=sector_tags,
        num_layers=num_layers,
        max_iterations=max_iterations,
    )


# ── Private helpers ───────────────────────────────────────────────────────────


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
