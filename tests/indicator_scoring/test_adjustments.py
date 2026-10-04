from __future__ import annotations

import unittest
from copy import deepcopy

import pandas as pd

from dc_locator.indicator_scoring import (
    apply_pre_weight_adjustments,
    load_adjustments_config,
    load_config,
    load_robustness_factors,
)


SCORING = load_config()
ADJUSTMENTS = load_adjustments_config()


def synthetic_scored(rows: int = 1) -> pd.DataFrame:
    data = {
        "fips": [f"0000{i + 1}" for i in range(rows)],
        "county_name": [f"County {i + 1}" for i in range(rows)],
        "state": ["VA"] * rows,
    }
    data.update({dimension: [0.5] * rows for dimension in SCORING["dimensions"]})
    data.update({f"u__{metric}": [100.0] * rows for metric in SCORING["indicators"]})
    return pd.DataFrame(data)


class MarginTests(unittest.TestCase):
    def test_weakest_margin_is_applied_once(self):
        scored = synthetic_scored()
        scored.loc[0, "u__baseline_water_stress"] = 25.0
        config = deepcopy(ADJUSTMENTS)
        config["robustness"]["enabled"] = False
        result = apply_pre_weight_adjustments(scored, SCORING, config)
        self.assertAlmostEqual(result.loc[0, "margin_headroom__baseline_water_stress"], 0.25)
        self.assertAlmostEqual(result.loc[0, "margin_factor__baseline_water_stress"], 0.85)
        self.assertAlmostEqual(result.loc[0, "margin_adjustment"], 0.85)
        self.assertEqual(result.loc[0, "margin_limiting_indicator"], "baseline_water_stress")

    def test_hard_zero_only_uses_explicit_indicators(self):
        scored = synthetic_scored(2)
        scored.loc[0, "u__labor_force"] = 0.0
        scored.loc[1, "u__baseline_water_stress"] = 0.0
        config = deepcopy(ADJUSTMENTS)
        config["robustness"]["enabled"] = False
        config["hard_zero_gate"] = {"enabled": True, "indicators": ["baseline_water_stress"]}
        result = apply_pre_weight_adjustments(scored, SCORING, config)
        self.assertEqual(result.loc[0, "normalization_gate_status"], "pass")
        self.assertEqual(result.loc[1, "normalization_gate_status"], "fail")
        self.assertEqual(result.loc[1, "normalization_gate_failed_indicators"], "baseline_water_stress")


class RobustnessTests(unittest.TestCase):
    def test_each_factor_changes_only_its_mapped_dimension(self):
        scored = synthetic_scored()
        factors = pd.DataFrame(
            {
                "fips": ["00001"],
                "heat_risk_percentile": [0.5],
                "cooling_climate_robustness_factor": [0.9],
                "dry_risk_percentile": [1.0],
                "water_robustness_factor": [0.8],
                "heavy_rain_risk_percentile": [0.25],
                "climate_risk_robustness_factor": [0.95],
            }
        )
        result = apply_pre_weight_adjustments(scored, SCORING, ADJUSTMENTS, factors)
        self.assertAlmostEqual(result.loc[0, "cooling_climate"], 0.45)
        self.assertAlmostEqual(result.loc[0, "water"], 0.4)
        self.assertAlmostEqual(result.loc[0, "climate_risk"], 0.475)
        self.assertAlmostEqual(result.loc[0, "land_ecology"], 0.5)
        self.assertAlmostEqual(result.loc[0, "base__cooling_climate"], 0.5)

    def test_shipped_table_has_full_version_locked_coverage(self):
        table = load_robustness_factors(ADJUSTMENTS)
        self.assertEqual(len(table), 292)
        self.assertEqual(table["fips"].nunique(), 292)
        self.assertTrue(table["cooling_climate_robustness_factor"].between(0.8, 1.0).all())
        self.assertTrue(table["water_robustness_factor"].between(0.8, 1.0).all())
        self.assertTrue(table["climate_risk_robustness_factor"].between(0.8, 1.0).all())


if __name__ == "__main__":
    unittest.main()
