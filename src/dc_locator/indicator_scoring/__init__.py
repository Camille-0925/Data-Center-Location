"""Raw indicators -> utility scores (0-100) -> dimension scores (0-1)."""

from .aggregation import AGGREGATION_METHODS, aggregate_dimension

__all__ = ["AGGREGATION_METHODS", "aggregate_dimension"]
