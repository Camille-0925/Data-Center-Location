"""Decision matrix: optional gates, weighted suitability score, ranking, run comparison."""

from .matrix import (
    AGGREGATION_METHODS,
    DEFAULT_DIMENSION_ORDER,
    ContractError,
    aggregate_dimension,
    compare_runs,
    recommend,
    run_decision,
)

__all__ = [
    "AGGREGATION_METHODS",
    "DEFAULT_DIMENSION_ORDER",
    "ContractError",
    "aggregate_dimension",
    "recommend",
    "compare_runs",
    "run_decision",
]
