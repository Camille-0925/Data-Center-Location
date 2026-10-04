"""Piecewise-linear value functions: raw indicator value -> utility 0-100.

    low_better:   u = 100              if x <= T
                  u = 100 (L - x)/(L - T)   if T < x < L
                  u = 0                if x >= L
    high_better:  u = 0                if x <= L
                  u = 100 (x - L)/(T - L)   if L < x < T
                  u = 100              if x >= T

T is the ideal value (utility saturates at 100), L the unacceptable value (utility 0).
Fixed anchors make utilities comparable across states and stable when counties are added,
unlike min-max scaling of the current sample. ``transform="ln"`` applies the natural log to
the value and to both anchors (diminishing returns, e.g. labor force).

The optional ``exponential`` shape, u = 100 (1 - e^(-rho s)) / (1 - e^(-rho)) with s the linear
fraction, is a sensitivity variant (Kirkwood 1997): rho > 0 gives diminishing returns near T.
"""

from __future__ import annotations

import numpy as np


def _transform(values, transform: str | None):
    values = np.asarray(values, dtype=float)
    if transform is None:
        return values
    if transform == "ln":
        if np.any(values <= 0):
            raise ValueError("ln transform needs positive values")
        return np.log(values)
    raise ValueError(f"unknown transform: {transform}")


def utility(
    values,
    direction: str,
    ideal_T: float,
    unacceptable_L: float,
    transform: str | None = None,
    shape: str = "linear",
    rho: float = 0.0,
    floor: float = 0.0,
) -> np.ndarray:
    """Utility 0-100 for an array of raw values (NaN stays NaN)."""

    x = _transform(values, transform)
    t = float(_transform([ideal_T], transform)[0])
    l = float(_transform([unacceptable_L], transform)[0])
    if direction == "low_better":
        if not t < l:
            raise ValueError("low_better needs ideal_T < unacceptable_L")
        fraction = (l - x) / (l - t)
    elif direction == "high_better":
        if not t > l:
            raise ValueError("high_better needs ideal_T > unacceptable_L")
        fraction = (x - l) / (t - l)
    else:
        raise ValueError(f"direction must be low_better or high_better, got {direction}")
    fraction = np.clip(fraction, 0.0, 1.0)
    if shape == "exponential":
        if rho == 0:
            raise ValueError("exponential shape needs a nonzero rho")
        fraction = (1 - np.exp(-rho * fraction)) / (1 - np.exp(-rho))
    elif shape != "linear":
        raise ValueError(f"unknown shape: {shape}")
    if not 0 <= floor < 100:
        raise ValueError("floor must be in [0, 100)")
    return np.where(np.isnan(fraction), np.nan, floor + (100 - floor) * fraction)
