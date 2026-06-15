"""Optimization engines package.

This package contains the classical and quantum optimization engines:

- ``classical``: Markowitz Mean-Variance Optimization via CVXPY.
- ``quantum``: QUBO formulation, QAOA (Qiskit), and VQE (PennyLane) solvers.

Usage::

    from app.engines.classical import ClassicalOptimizer, OptimizationResult
    from app.engines.classical.schemas import (
        ClassicalOptimizationInput,
        ClassicalOptimizationResult,
        OptimizationConstraints,
    )
"""
