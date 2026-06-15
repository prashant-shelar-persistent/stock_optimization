"""Quantum Optimization Engine — QUBO + QAOA (Qiskit) + VQE (PennyLane).

This package implements the quantum optimization layer of the Portfolio
Optimizer. It converts the asset-selection problem into a QUBO (Quadratic
Unconstrained Binary Optimization) formulation and solves it using two
complementary quantum algorithms:

1. **QAOA** (Quantum Approximate Optimization Algorithm) via Qiskit 1.1.x
   and qiskit-optimization 0.6.x, running on the Qiskit Aer statevector
   simulator.

2. **VQE-style** (Variational Quantum Eigensolver) via PennyLane 0.36.x,
   using a hardware-efficient ansatz on the ``default.qubit`` simulator.

Both solvers fall back to a greedy classical selection strategy when the
quantum libraries are unavailable (e.g. in lightweight CI environments).

Public API
----------
The primary entry point is :func:`run_quantum_optimization` from the
:mod:`dispatcher` module. The lower-level QUBO builder and individual
solvers are also exported for direct use in tests and the agent layer.

Example::

    from app.quantum import run_quantum_optimization

    result = run_quantum_optimization(
        tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        constraints={"num_assets_to_select": 2},
    )
    print(result.qaoa.metrics.sharpe_ratio)
    print(result.vqe.metrics.sharpe_ratio)
"""
from __future__ import annotations

from app.quantum.dispatcher import run_quantum_optimization
from app.quantum.qaoa_solver import run_qaoa
from app.quantum.qubo import build_qubo_matrix, decode_bitstring, qubo_energy
from app.quantum.vqe_solver import run_vqe


__all__ = [
    # Primary dispatcher
    "run_quantum_optimization",
    # QUBO utilities
    "build_qubo_matrix",
    "decode_bitstring",
    "qubo_energy",
    # Individual solvers
    "run_qaoa",
    "run_vqe",
]
