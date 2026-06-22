"""Quantum optimization engine package.

This package implements the quantum optimization pipeline for portfolio
asset selection using QUBO (Quadratic Unconstrained Binary Optimization)
formulations solved by QAOA (Qiskit) and VQE (PennyLane).

Architecture
------------
The package is organised into the following modules:

- ``schemas``: Pydantic v2 input/output schemas for the quantum engine.
- ``base``: Abstract base class for quantum solvers.
- ``qubo``: QUBO matrix formulation and utilities.
- ``qaoa_qiskit``: QAOA solver using Qiskit Aer simulator.
- ``vqe_pennylane``: VQE-style solver using PennyLane.
- ``metrics``: Portfolio metrics and solution quality computation.
- ``dispatcher``: Orchestrates the full quantum optimization pipeline.

Primary entry points
--------------------
- :class:`QuantumDispatcher` — the main class for running quantum optimization.
- :func:`run_quantum_optimization` — convenience function for dict-based usage.
- :class:`QAOASolver` — QAOA solver (can be used directly for testing).
- :class:`VQESolver` — VQE solver (can be used directly for testing).

Usage::

    from app.engines.quantum import (
        QuantumDispatcher,
        QuantumOptimizationInput,
        QuantumOptimizationConstraints,
        QuantumOptimizationResult,
        run_quantum_optimization,
    )
    import numpy as np

    # High-level API via dispatcher
    dispatcher = QuantumDispatcher()
    result = dispatcher.optimize(
        QuantumOptimizationInput(
            tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
            expected_returns=[0.12, 0.10, 0.09, 0.15],
            cov_matrix=sigma.tolist(),
            constraints=QuantumOptimizationConstraints(num_assets_to_select=2),
            budget=100_000.0,
        )
    )

    # Convenience function API
    result = run_quantum_optimization(
        tickers=["AAPL", "MSFT", "GOOGL", "AMZN"],
        expected_returns=mu,
        covariance_matrix=sigma,
        budget=100_000.0,
        constraints={"num_assets_to_select": 2},
    )

    if result.qaoa:
        print("QAOA Sharpe:", result.qaoa.metrics.sharpe_ratio)
    if result.vqe:
        print("VQE Sharpe:", result.vqe.metrics.sharpe_ratio)
    print("Best algorithm:", result.best_algorithm)
"""
from app.engines.quantum.base import BaseQuantumSolver
from app.engines.quantum.dispatcher import QuantumDispatcher, run_quantum_optimization
from app.engines.quantum.qaoa_qiskit import QAOASolver, run_qaoa
from app.engines.quantum.qubo import QUBOMetadata, build_qubo
from app.engines.quantum.schemas import (
    QuantumAssetResult,
    QuantumAssetWeight,
    QuantumOptimizationConstraints,
    QuantumOptimizationInput,
    QuantumOptimizationResult,
    QuantumPortfolioMetrics,
)
from app.engines.quantum.vqe_pennylane import VQESolver, run_vqe


__all__ = [
    # Dispatcher (primary entry point)
    "QuantumDispatcher",
    "run_quantum_optimization",
    # Solvers
    "QAOASolver",
    "VQESolver",
    "run_qaoa",
    "run_vqe",
    # Base class
    "BaseQuantumSolver",
    # Schemas
    "QuantumOptimizationInput",
    "QuantumOptimizationConstraints",
    "QuantumOptimizationResult",
    "QuantumAssetResult",
    "QuantumAssetWeight",
    "QuantumPortfolioMetrics",
    # QUBO utilities
    "build_qubo",
    "QUBOMetadata",
]
