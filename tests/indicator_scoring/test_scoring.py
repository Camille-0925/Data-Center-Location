from __future__ import annotations

import math
import unittest
from copy import deepcopy

import numpy as np

from dc_locator.data_prep import load_processed
from dc_locator.indicator_scoring import (
    dimension_score_records,
    load_config,
    score_counties,
    utility,
    validate_config,
)

CONFIG = load_config()


class UtilityTests(unittest.TestCase):
    def test_low_better_piecewise(self):
        u = utility([0.5, 1.0, 2.5, 4.0, 5.0], "low_better", 1.0, 4.0)
        self.assertTrue(np.allclose(u, [100, 100, 50, 0, 0]))

    def test_high_better_piecewise(self):
        u = utility([0.0, 0.45, 0.9, 1.0], "high_better", 0.9, 0.0)
        self.assertTrue(np.allclose(u, [0, 50, 100, 100]))

    def test_carbon_example_from_the_slide(self):
        # T = 100, L = 650, x = 300  ->  100 * (650 - 300) / (650 - 100) = 63.6
        self.assertAlmostEqual(float(utility([300], "low_better", 100, 650)[0]), 63.636, places=3)

    def test_log_transform_applies_to_value_and_anchors(self):
        midpoint = math.exp((math.log1p(2000) + math.log1p(50000)) / 2) - 1
        u = utility([2000, midpoint, 50000], "high_better", 50000, 2000, transform="ln")
        self.assertTrue(np.allclose(u, [0, 50, 100]))

    def test_exponential_shape_bends_but_keeps_end_points(self):
        u = utility([1.0, 2.5, 4.0], "low_better", 1.0, 4.0, shape="exponential", rho=2.0)
        self.assertAlmostEqual(u[0], 100)
        self.assertAlmostEqual(u[2], 0)
        self.assertGreater(u[1], 50)

    def test_missing_value_stays_missing_and_floor_applies(self):
        u = utility([np.nan, 4.0], "low_better", 1.0, 4.0, floor=1.0)
        self.assertTrue(np.isnan(u[0]))
        self.assertAlmostEqual(u[1], 1.0)

    def test_invalid_anchor_order_is_rejected(self):
        with self.assertRaises(ValueError):
            utility([1], "low_better", 4.0, 1.0)
        with self.assertRaises(ValueError):
            utility([1], "sideways", 1.0, 4.0)


class ConfigTests(unittest.TestCase):
    def test_shipped_config_is_valid(self):
        validate_config(CONFIG)
        self.assertEqual(len(CONFIG["dimensions"]), 8)
        self.assertEqual(len(CONFIG["indicators"]), 18)
        self.assertEqual(CONFIG["value_function"], "clipped_piecewise_linear")

    def test_weights_must_sum_to_one(self):
        config = deepcopy(CONFIG)
        config["dimensions"]["transportation"]["weights"]["distance_to_rail_km"] = 0.6
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_indicator_in_wrong_dimension_is_rejected(self):
        config = deepcopy(CONFIG)
        config["dimensions"]["water"]["weights"] = {"historical_cdd65": 1.0}
        with self.assertRaises(ValueError):
            validate_config(config)


class CountyScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = load_processed()
        cls.scored = score_counties(cls.table, CONFIG)
        cls.loudoun = cls.scored[cls.scored["fips"] == "51107"].iloc[0]

    def test_all_counties_get_eight_scores_in_range(self):
        dims = list(CONFIG["dimensions"])
        self.assertEqual(len(self.scored), 292)
        values = self.scored[dims].to_numpy()
        self.assertFalse(np.isnan(values).any())
        self.assertTrue(((values >= 0) & (values <= 1)).all())

    def test_raw_values_and_piecewise_results_are_both_auditable(self):
        for metric_id in CONFIG["indicators"]:
            self.assertIn(f"raw__{metric_id}", self.scored)
            self.assertIn(f"u__{metric_id}", self.scored)

    def test_loudoun_climate_is_mean_of_fixed_anchor_utilities(self):
        wildfire = (0.9 - 0.257) / (0.9 - 0.2)
        flood = (0.8 - 0.1819306930693069) / (0.8 - 0.1)
        expected = (wildfire + flood) / 2
        self.assertAlmostEqual(self.loudoun["climate_risk"], expected, places=9)

    def test_loudoun_water_is_the_mean_of_baseline_and_2050(self):
        baseline = 1.0  # 0.306 is below T = 1
        future = 1.0  # 0.599 is also below T = 1
        self.assertAlmostEqual(self.loudoun["water"], (baseline + future) / 2, places=9)

    def test_loudoun_land_is_equal_weight_mean(self):
        u_open = (0.775497584437608 - 0.25) / (0.98 - 0.25)
        u_protected = 1 - 0.0051825238339239 / 0.25
        u_wetland = 1 - 0.0149899382239743 / 0.4
        expected = (u_open + u_protected + u_wetland) / 3
        self.assertAlmostEqual(self.loudoun["land_ecology"], expected, places=9)

    def test_loudoun_transport_is_equal_weight_mean(self):
        u_interstate = (50 - 27.93260053074667) / 45
        u_rail = 0.0  # 20.2604 km is beyond L = 20 km
        self.assertAlmostEqual(self.loudoun["transportation"], (u_interstate + u_rail) / 2, places=9)

    def test_energy_is_constant_within_each_state(self):
        self.assertTrue((self.scored.groupby("state")["energy_carbon"].nunique() == 1).all())

    def test_context_views_are_retained_for_scored_indicators(self):
        self.assertAlmostEqual(self.loudoun["water_stress_change_2050"], 0.5991993213842712 - 0.3058479616917511)
        self.assertIn(self.loudoun["social_vulnerability_band"], {"low", "low-moderate", "moderate-high", "high"})
        self.assertIn(self.loudoun["extreme_heat_days_band"], {"normal", "elevated", "high", "extreme"})
        self.assertIn("u__social_vulnerability_percentile", self.scored.columns)
        self.assertIn("u__fiber_business_100_20_availability", self.scored.columns)
        self.assertIn("u__historical_days_tmax_gt90f", self.scored.columns)

    def test_records_feed_the_decision_matrix(self):
        records = dimension_score_records(self.scored[self.scored["state"] == "VA"], list(CONFIG["dimensions"]))
        self.assertEqual(len(records), 133)
        self.assertEqual(set(records[0]["scores"]), set(CONFIG["dimensions"]))
        self.assertTrue(records[0]["candidate_name"].endswith(", VA"))


if __name__ == "__main__":
    unittest.main()
