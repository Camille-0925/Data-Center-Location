"""Decision matrix: n x K dimension scores + K weights -> score, rank, Pareto, trade-offs."""

from .matrix import (
    DEFAULT_DIMENSION_ORDER,
    ContractError,
    compare_runs,
    recommend,
    run_decision,
)

__all__ = ["DEFAULT_DIMENSION_ORDER", "ContractError", "recommend", "compare_runs", "run_decision"]
