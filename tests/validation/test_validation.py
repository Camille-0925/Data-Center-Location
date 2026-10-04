from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from dc_locator.validation.methods import critic_weights, entropy_weights, equal_weights, roc_weights
from dc_locator.validation.smaa import choquet_scores, lambda_max, smaa


class MethodTests(unittest.TestCase):
    def test_roc_matches_published_values_for_four_criteria(self):
        w = roc_weights(["a", "b", "c", "d"])
        self.assertTrue(np.allclose([w["a"], w["b"], w["c"], w["d"]], [0.5208, 0.2708, 0.1458, 0.0625], atol=1e-4))

    def test_equal_weights(self):
        self.assertEqual(equal_weights(["a", "b"]), {"a": 0.5, "b": 0.5})

    def test_critic_rewards_spread_and_independence(self):
        # "flat" is uncorrelated with "spread" but barely varies; "copy" duplicates "spread".
        frame = pd.DataFrame({"spread": [0.0, 1.0, 0.0, 1.0], "flat": [0.5, 0.5, 0.52, 0.52], "copy": [0.0, 1.0, 0.0, 1.0]})
        w = critic_weights(frame, ["spread", "flat", "copy"])
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertGreater(w["spread"], w["flat"])
        self.assertAlmostEqual(w["spread"], w["copy"])

    def test_critic_is_undefined_when_all_dimensions_move_together(self):
        frame = pd.DataFrame({"a": [0.0, 1.0, 0.0, 1.0], "b": [0.5, 0.52, 0.5, 0.52]})  # perfectly correlated
        with self.assertRaises(ValueError):
            critic_weights(frame, ["a", "b"])


    def test_entropy_gives_no_weight_to_a_constant_dimension(self):
        frame = pd.DataFrame({"varies": [0.1, 0.9, 0.5], "constant": [0.4, 0.4, 0.4]})
        w = entropy_weights(frame, ["varies", "constant"])
        self.assertAlmostEqual(w["constant"], 0.0, places=6)


class SmaaTests(unittest.TestCase):
    def test_lambda_max_is_the_binding_ratio(self):
        weights = np.array([[0.2, 0.3, 0.5]])
        index = {"a": 0, "b": 1, "c": 2}
        lam = lambda_max(weights, index, [("a", "b", 0.8), ("b", "c", -0.4)])
        # loads: a 0.4, b 0.6, c 0.2 -> ratios 0.5, 0.5, 2.5
        self.assertAlmostEqual(lam[0], 0.5)

    def test_choquet_scores_match_the_formula(self):
        D = np.array([[0.9, 0.1], [0.5, 0.5]])
        weights = np.array([[0.5, 0.5]])
        scores = choquet_scores(D, weights, np.array([1.0]), {"w": 0, "c": 1}, [("w", "c", 1.0)])
        # lambda_max = 0.5 / 0.5 = 1, I = 1 -> 0.5 - 0.5 * 0.8 = 0.1 and 0.5
        self.assertTrue(np.allclose(scores, [[10.0, 50.0]]))

    def test_dominant_county_wins_every_sample(self):
        D = pd.DataFrame({"x": [0.9, 0.5, 0.1], "y": [0.9, 0.4, 0.2]}, index=["best", "mid", "low"])
        result = smaa(D, {"x": 0.5, "y": 0.5}, [], samples=500, top=2)
        self.assertEqual(result["table"].loc["best", "p_top1"], 1.0)
        self.assertEqual(result["table"].loc["low", "p_top2"], 0.0)
        self.assertEqual(result["most_robust"], "best")

    def test_rank_acceptabilities_sum_to_one_per_rank(self):
        rng = np.random.default_rng(0)
        D = pd.DataFrame(rng.random((12, 3)), columns=["a", "b", "c"])
        result = smaa(D, {"a": 0.3, "b": 0.3, "c": 0.4}, [("a", "b", 0.5)], samples=300, top=5)
        self.assertTrue(np.allclose(result["rank_acceptability"].sum(axis=0), 1.0))

    def test_dirichlet_samples_are_centred_on_the_customer_weights(self):
        D = pd.DataFrame({"a": [0.1, 0.9], "b": [0.5, 0.5]})
        result = smaa(D, {"a": 0.7, "b": 0.3}, [], samples=4000, alpha=20)
        self.assertAlmostEqual(result["settings"]["weight_mean"]["a"], 0.7, delta=0.01)

    def test_zero_weight_dimensions_are_ignored(self):
        D = pd.DataFrame({"a": [0.9, 0.1], "b": [0.1, 0.9], "energy": [0.5, 0.5]}, index=["p", "q"])
        result = smaa(D, {"a": 0.8, "b": 0.2, "energy": 0.0}, [("a", "energy", 0.5)], samples=200)
        self.assertNotIn("energy", result["settings"]["weight_mean"])


class ConsistencyTests(unittest.TestCase):
    def test_final_multiplier_scales_smaa_scores(self):
        D = pd.DataFrame({"x": [0.9, 0.8], "y": [0.9, 0.8]}, index=["a", "b"])
        plain = smaa(D, {"x": 0.5, "y": 0.5}, [], samples=200)
        flipped = smaa(D, {"x": 0.5, "y": 0.5}, [], samples=200,
                       final_multiplier=pd.Series({"a": 0.8, "b": 1.0}))
        self.assertEqual(plain["most_robust"], "a")
        self.assertEqual(flipped["most_robust"], "b")  # 0.9 * 0.8 < 0.8 * 1.0

    def test_smaa_agrees_with_the_pipeline_final_ranking(self):
        from dc_locator.validation import run_validation
        result = run_validation("VA", samples=500)
        final_first = result["baseline"]["ranking"]["fips"].iloc[0]
        top10 = set(result["smaa_table"].index[:10])
        self.assertIn(final_first, top10)
        self.assertEqual(result["methods"]["summary"].iloc[1]["first"],
                         result["baseline"]["counties"].set_index("fips").loc[final_first, "county_name"])


class AdjustmentSamplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dc_locator.pipeline import run
        from dc_locator.validation.smaa import raw_interaction_pattern

        cls.baseline = run("VA")
        cls.counties = cls.baseline["counties"].set_index("fips")
        cls.pattern = raw_interaction_pattern(cls.baseline["interactions"]["pairs"])

    def _run(self, **kwargs):
        return smaa(self.counties, self.baseline["weights"]["weights"], self.pattern, samples=200, seed=3, **kwargs)

    def test_fixed_lambdas_reproduce_the_pipeline_factors(self):
        from dc_locator.validation import adjustment_inputs, final_multiplier

        sampled = self._run(adjustments=adjustment_inputs(self.baseline, (0.2, 0.2)))["table"]
        fixed = self._run(final_multiplier=final_multiplier(self.baseline))["table"]
        self.assertTrue(np.allclose(sampled["regret_q90"], fixed["regret_q90"].reindex(sampled.index)))

    def test_zero_lambdas_remove_both_adjustments(self):
        from dc_locator.validation import adjustment_inputs

        inputs = adjustment_inputs(self.baseline, (0.0, 0.0))
        base = inputs["base"]
        sampled = self._run(adjustments=inputs)["table"]
        unadjusted = smaa(base, self.baseline["weights"]["weights"], self.pattern, samples=200, seed=3)["table"]
        self.assertTrue(np.allclose(sampled["regret_q90"], unadjusted["regret_q90"].reindex(sampled.index)))

    def test_effective_shares_sum_to_one(self):
        from dc_locator.validation import effective_weights

        shares = effective_weights(self.baseline)
        self.assertAlmostEqual(shares["effective_share"].sum(), 1.0)

    def test_sampled_ranges_are_reported(self):
        from dc_locator.validation import adjustment_inputs

        settings = self._run(adjustments=adjustment_inputs(self.baseline))["settings"]
        self.assertEqual(settings["lambda_m_range"], [0.1, 0.3])
        self.assertEqual(set(settings["robustness_dimensions"]), {"cooling_climate", "water", "climate_risk"})


if __name__ == "__main__":
    unittest.main()
