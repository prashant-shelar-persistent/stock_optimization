"""Classical optimization engine package.

Exports the main optimizer class and result type for use by the agent layer
and API layer.

Usage::

    from app.engines.classical import ClassicalOptimizer, OptimizationResult
    from app.engines.classical.schemas import (
        ClassicalOptimizationInput,
        ClassicalOptimizationResult,
        OptimizationConstraints,
    )

    optimizer = ClassicalOptimizer()
    result = optimizer.optimize(input_data)
    print(result.weights)
    print(result.sharpe_ratio)
"""
from app.engines.classical.optimizer import ClassicalOptimizer
from app.engines.classical.schemas import (
    ClassicalOptimizationInput,
    ClassicalOptimizationResult,
    OptimizationConstraints,
)


# Alias for backward compatibility / convenience
OptimizationResult = ClassicalOptimizationResult

__all__ = [
    "ClassicalOptimizationInput",
    "ClassicalOptimizationResult",
    "ClassicalOptimizer",
    "OptimizationConstraints",
    "OptimizationResult",
]
