from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from dc_locator.interactions import build_interactions, spearman_matrix

ORDER = ["a", "b", "c", "d"]


def corr(values):
    frame = pd.DataFrame(np.eye(4), index=ORDER, columns=ORDER)
    for (k, l), rho in values.items():
        frame.loc[k, l] = frame.loc[l, k] = rho
    return frame


class InteractionMatrixTests(unittest.TestCase):
    def test_complementarity_uses_dematel_only(self):
        result = build_interactions(
            ORDER, {d: 0.25 for d in ORDER}, {("a", "b"): 0.8}, corr({("a", "b"): -0.9}),
            [{"dimensions": ["a", "b"], "type": "complementarity"}], kappa=1.0,
        )
        pair = result["pairs"][0]
        self.assertAlmostEqual(pair["strength"], 0.8)
        self.assertGreater(result["interactions"][0]["value"], 0)

    def test_redundancy_mixes_dematel_and_positive_correlation(self):
        result = build_interactions(
            ORDER, {d: 0.25 for d in ORDER}, {("a", "b"): 0.8}, corr({("a", "b"): 0.4}),
            [{"dimensions": ["a", "b"], "type": "redundancy"}], kappa=1.0, beta=0.5,
        )
        self.assertAlmostEqual(result["pairs"][0]["strength"], 0.5 * 0.8 + 0.5 * 0.4)
        self.assertLess(result["interactions"][0]["value"], 0)

    def test_redundancy_without_data_support_is_dropped(self):
        result = build_interactions(
            ORDER, {d: 0.25 for d in ORDER}, {("a", "b"): 1.0}, corr({("a", "b"): -0.2}),
            [{"dimensions": ["a", "b"], "type": "redundancy"}],
        )
        self.assertEqual(result["interactions"], [])
        self.assertIn("not supported", result["pairs"][0]["status"])
        self.assertTrue(result["warnings"])

    def test_zero_weight_dimension_gets_no_interaction(self):
        weights = {"a": 0.5, "b": 0.5, "c": 0.0, "d": 0.0}
        result = build_interactions(
            ORDER, weights, {("a", "c"): 1.0}, corr({}), [{"dimensions": ["a", "c"], "type": "complementarity"}],
        )
        self.assertEqual(result["interactions"], [])

    def test_kappa_one_reaches_the_monotonicity_bound_exactly(self):
        weights = {"a": 0.1, "b": 0.4, "c": 0.25, "d": 0.25}
        result = build_interactions(
            ORDER, weights, {("a", "b"): 1.0, ("a", "c"): 0.5}, corr({}),
            [{"dimensions": ["a", "b"], "type": "complementarity"}, {"dimensions": ["a", "c"], "type": "complementarity"}],
            kappa=1.0,
        )
        self.assertEqual(result["binding_dimension"], "a")
        load_a = sum(abs(i["value"]) for i in result["interactions"] if "a" in i["dimensions"]) / 2
        self.assertAlmostEqual(load_a, weights["a"])  # phi_a = 1/2 sum |I_a.| at kappa = 1

    def test_kappa_scales_linearly_and_keeps_the_pattern(self):
        args = (ORDER, {d: 0.25 for d in ORDER}, {("a", "b"): 1.0, ("c", "d"): 0.5}, corr({}),
                [{"dimensions": ["a", "b"], "type": "complementarity"}, {"dimensions": ["c", "d"], "type": "complementarity"}])
        half = {tuple(i["dimensions"]): i["value"] for i in build_interactions(*args, kappa=0.5)["interactions"]}
        full = {tuple(i["dimensions"]): i["value"] for i in build_interactions(*args, kappa=1.0)["interactions"]}
        for key in full:
            self.assertAlmostEqual(half[key], full[key] / 2)
        self.assertAlmostEqual(full[("a", "b")] / full[("c", "d")], 2.0)

    def test_invalid_inputs_are_rejected(self):
        base = (ORDER, {d: 0.25 for d in ORDER}, {}, corr({}))
        with self.assertRaises(ValueError):
            build_interactions(*base, [{"dimensions": ["a", "b"], "type": "synergy"}])
        with self.assertRaises(ValueError):
            build_interactions(*base, [{"dimensions": ["a", "a"], "type": "redundancy"}])
        with self.assertRaises(ValueError):
            build_interactions(*base, [{"dimensions": ["a", "b"], "type": "redundancy"},
                                       {"dimensions": ["b", "a"], "type": "redundancy"}])
        with self.assertRaises(ValueError):
            build_interactions(*base, [], kappa=1.5)

    def test_spearman_handles_constant_dimension(self):
        frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 9], "c": [5, 5, 5, 5], "d": [4, 3, 2, 1]})
        matrix, constant = spearman_matrix(frame, ORDER)
        self.assertEqual(constant, ["c"])
        self.assertAlmostEqual(matrix.loc["a", "b"], 1.0)
        self.assertAlmostEqual(matrix.loc["a", "d"], -1.0)
        self.assertEqual(matrix.loc["a", "c"], 0.0)


if __name__ == "__main__":
    unittest.main()
