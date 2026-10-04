from __future__ import annotations

from copy import deepcopy
import itertools
import unittest

import numpy as np

from dc_locator.dimension_weights import (
    ahp_weights,
    apply_cap,
    build_matrix,
    compute_dimension_weights,
    eigenvector_priorities,
    load_config,
)

CONFIG = load_config()
ORDER = CONFIG["dimension_order"]


def consistent_judgments(order, weights):
    return [[a, b, weights[a] / weights[b]] for a, b in itertools.combinations(order, 2)]


class AhpTests(unittest.TestCase):
    def test_perfectly_consistent_matrix_recovers_weights(self):
        order = ["a", "b", "c", "d"]
        truth = {"a": 0.4, "b": 0.3, "c": 0.2, "d": 0.1}
        result = ahp_weights(order, [{"respondent_id": "x", "judgments": consistent_judgments(order, truth)}])
        for d in order:
            self.assertAlmostEqual(result["weights"][d], truth[d])
            self.assertAlmostEqual(result["weights_geometric_mean"][d], truth[d])
        self.assertAlmostEqual(result["consistency_ratio"], 0.0, places=9)

    def test_draft_matrix_is_consistent_and_methods_agree(self):
        result = compute_dimension_weights(mode="cross_state")["ahp"]
        self.assertLess(result["consistency_ratio"], 0.10)
        self.assertLess(result["max_method_gap"], 0.01)
        self.assertAlmostEqual(sum(result["base_weights"].values()), 1.0)

    def test_inconsistent_matrix_is_rejected(self):
        order = ["a", "b", "c"]
        judgments = [["a", "b", 9], ["b", "c", 9], ["a", "c", 1 / 9]]  # a >> b >> c but c >> a
        with self.assertRaises(ValueError):
            ahp_weights(order, [{"respondent_id": "x", "judgments": judgments}])

    def test_reciprocal_matrix_and_scale_checks(self):
        matrix = build_matrix(["a", "b"], [["a", "b", 3]])
        self.assertAlmostEqual(matrix[1, 0], 1 / 3)
        with self.assertRaises(ValueError):
            build_matrix(["a", "b"], [["a", "b", 12]])
        with self.assertRaises(ValueError):
            build_matrix(["a", "b", "c"], [["a", "b", 2]])  # missing pairs

    def test_group_judgments_use_geometric_mean(self):
        order = ["a", "b"]
        result = ahp_weights(order, [
            {"respondent_id": "p", "judgments": [["a", "b", 4]]},
            {"respondent_id": "q", "judgments": [["a", "b", 1]]},
        ])
        # geometric mean of 4 and 1 is 2, so a : b = 2 : 1
        self.assertAlmostEqual(result["weights"]["a"], 2 / 3)
        self.assertEqual(len(result["respondents"]), 2)

    def test_eigenvector_of_identity_like_matrix_is_uniform(self):
        vector, lam = eigenvector_priorities(np.ones((5, 5)))
        self.assertTrue(np.allclose(vector, 0.2))
        self.assertAlmostEqual(lam, 5.0)


class CustomerInputTests(unittest.TestCase):
    def setUp(self):
        self.default = compute_dimension_weights()

    def test_default_inputs_give_reference_weights(self):
        self.assertEqual(self.default["multiplier_trace"], [])
        for d in ORDER:
            self.assertAlmostEqual(self.default["weights"][d], self.default["reference_weights"][d])

    def test_within_state_excludes_energy_and_renormalizes(self):
        weights = self.default["weights"]
        base = self.default["ahp"]["base_weights"]
        self.assertEqual(weights["energy_carbon"], 0.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["water"], base["water"] / (1 - base["energy_carbon"]))

    def test_cross_state_keeps_all_eight_dimensions(self):
        result = compute_dimension_weights(mode="cross_state")
        for d in ORDER:
            self.assertAlmostEqual(result["weights"][d], result["ahp"]["base_weights"][d])

    def test_every_option_moves_its_target_dimension_in_the_right_direction(self):
        for field, spec in CONFIG["customer_inputs"].items():
            for choice, factors in spec["options"].items():
                result = compute_dimension_weights({field: choice}, mode="cross_state")
                for dimension_id, factor in factors.items():
                    change = result["weights"][dimension_id] - result["reference_weights"][dimension_id]
                    if factor > 1:
                        self.assertGreater(change, 0, f"{field}={choice} should raise {dimension_id}")
                    elif factor < 1:
                        self.assertLess(change, 0, f"{field}={choice} should lower {dimension_id}")

    def test_ratio_scale_is_preserved(self):
        result = compute_dimension_weights({"latency_sensitivity": "high"}, mode="cross_state")
        base = result["ahp"]["base_weights"]
        w = result["weights"]
        self.assertAlmostEqual(w["fiber_connectivity"] / w["water"], 1.6 * base["fiber_connectivity"] / base["water"])
        self.assertAlmostEqual(w["climate_risk"] / w["water"], base["climate_risk"] / base["water"])

    def test_all_combinations_sum_to_one_and_respect_cap(self):
        spec = CONFIG["customer_inputs"]
        fields = list(spec)
        for combo in itertools.product(*(spec[f]["options"] for f in fields)):
            for mode in ("within_state", "cross_state"):
                result = compute_dimension_weights(dict(zip(fields, combo)), mode=mode)
                self.assertAlmostEqual(sum(result["weights"].values()), 1.0)
                self.assertTrue(all(0 <= w <= CONFIG["max_dimension_weight"] + 1e-12 for w in result["weights"].values()))

    def test_cap_redistributes_excess_pro_rata(self):
        weights, capped = apply_cap({"a": 0.7, "b": 0.2, "c": 0.1}, 0.4)
        self.assertEqual(capped, ["a"])
        self.assertAlmostEqual(weights["a"], 0.4)
        self.assertAlmostEqual(weights["b"] / weights["c"], 2.0)
        self.assertAlmostEqual(sum(weights.values()), 1.0)

    def test_infeasible_cap_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_cap({"a": 0.5, "b": 0.5}, 0.4)

    def test_unknown_input_or_option_is_rejected(self):
        with self.assertRaises(ValueError):
            compute_dimension_weights({"budget": "low"})
        with self.assertRaises(ValueError):
            compute_dimension_weights({"cooling_type": "seawater"})

    def test_trace_explains_each_multiplier(self):
        result = compute_dimension_weights({"cooling_type": "air_economizer"})
        self.assertEqual(
            {(t["dimension_id"], t["multiplier"]) for t in result["multiplier_trace"]},
            {("water", 0.6), ("cooling_climate", 1.5)},
        )

    def test_replacing_the_ahp_respondent_changes_the_base(self):
        config = deepcopy(CONFIG)
        equal = {d: 1 / 8 for d in ORDER}
        config["ahp"]["respondents"] = [{"respondent_id": "equal", "judgments": consistent_judgments(ORDER, equal)}]
        result = compute_dimension_weights(mode="cross_state", config=config)
        self.assertTrue(all(abs(w - 0.125) < 1e-9 for w in result["weights"].values()))


if __name__ == "__main__":
    unittest.main()
