from __future__ import annotations

import unittest

from dc_locator.indicator_scoring import aggregate_dimension


class AggregationTests(unittest.TestCase):
    def test_weighted_mean(self):
        self.assertAlmostEqual(aggregate_dimension("weighted_mean", [95, 30], [0.7, 0.3]), 0.755)

    def test_geometric_mean_penalizes_one_poor_indicator(self):
        # wildfire u = 90, flood u = 10: the mean would be 0.50, the geometric mean is 0.30
        self.assertAlmostEqual(aggregate_dimension("weighted_mean", [90, 10], [0.5, 0.5]), 0.50)
        self.assertAlmostEqual(aggregate_dimension("weighted_geometric", [90, 10], [0.5, 0.5]), 0.30)

    def test_weighted_geometric_uses_weights_as_exponents(self):
        value = aggregate_dimension("weighted_geometric", [100, 40, 40], [0.5, 0.25, 0.25])
        self.assertAlmostEqual(value, 0.4**0.5)

    def test_min_takes_the_worst_indicator(self):
        self.assertAlmostEqual(aggregate_dimension("min", [90, 20], [0.5, 0.5]), 0.20)

    def test_min_ignores_zero_weight_indicators(self):
        self.assertAlmostEqual(aggregate_dimension("min", [90, 0], [1.0, 0.0]), 0.90)

    def test_zero_score_zeroes_geometric_and_min(self):
        self.assertEqual(aggregate_dimension("weighted_geometric", [0, 100], [0.5, 0.5]), 0.0)
        self.assertEqual(aggregate_dimension("min", [0, 100], [0.5, 0.5]), 0.0)

    def test_equal_scores_give_the_same_result_for_every_method(self):
        for method in ("weighted_mean", "weighted_geometric", "min"):
            self.assertAlmostEqual(aggregate_dimension(method, [40, 40, 40], [0.5, 0.25, 0.25]), 0.40)

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            aggregate_dimension("median", [50], [1.0])
        with self.assertRaises(ValueError):
            aggregate_dimension("weighted_mean", [50, 50], [0.6, 0.6])
        with self.assertRaises(ValueError):
            aggregate_dimension("weighted_mean", [120], [1.0])
        with self.assertRaises(ValueError):
            aggregate_dimension("weighted_mean", [50, 50], [1.0])


if __name__ == "__main__":
    unittest.main()
