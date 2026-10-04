from __future__ import annotations

import unittest

import numpy as np

from dc_locator.interactions import dematel, direct_matrix, pairwise_strength, run_dematel, total_relation


class DematelTests(unittest.TestCase):
    def test_two_dimension_example_matches_hand_calculation(self):
        # Z = [[0, 2], [1, 0]] -> s = 2, X = [[0, 1], [0.5, 0]], T = X (I - X)^-1 = [[1, 2], [1, 1]]
        result = dematel(["a", "b"], [{"respondent_id": "x", "influences": {"a": {"b": 2}, "b": {"a": 1}}}])
        self.assertTrue(np.allclose(result["total_relation_matrix"], [[1, 2], [1, 1]]))
        a, b = result["dimensions"]
        self.assertAlmostEqual(a["relation_r_minus_c"], 1.0)
        self.assertEqual(a["role"], "cause")
        self.assertEqual(b["role"], "effect")
        self.assertAlmostEqual(a["prominence_r_plus_c"], 5.0)

    def test_total_relation_includes_indirect_chains(self):
        # a -> b -> c only; T must show an indirect a -> c influence
        order = ["a", "b", "c"]
        result = dematel(order, [{"respondent_id": "x", "influences": {"a": {"b": 4}, "b": {"c": 4}}}])
        t = np.array(result["total_relation_matrix"])
        self.assertGreater(t[0, 2], 0)
        self.assertEqual(t[2, 0], 0)

    def test_relations_sum_to_zero(self):
        result = run_dematel()
        self.assertAlmostEqual(sum(d["relation_r_minus_c"] for d in result["dimensions"]), 0.0)

    def test_draft_identifies_climate_as_main_cause_and_water_as_main_effect(self):
        result = run_dematel()
        ranked = sorted(result["dimensions"], key=lambda d: d["relation_r_minus_c"])
        self.assertEqual(ranked[-1]["dimension_id"], "climate_risk")
        self.assertEqual(ranked[0]["dimension_id"], "water")

    def test_respondents_are_averaged(self):
        order = ["a", "b"]
        result = dematel(order, [
            {"respondent_id": "p", "influences": {"a": {"b": 4}}},
            {"respondent_id": "q", "influences": {"a": {"b": 0}, "b": {"a": 2}}},
        ])
        self.assertEqual(result["direct_matrix"], [[0.0, 2.0], [1.0, 0.0]])

    def test_invalid_scores_are_rejected(self):
        with self.assertRaises(ValueError):
            direct_matrix(["a", "b"], {"a": {"b": 5}})
        with self.assertRaises(ValueError):
            direct_matrix(["a", "b"], {"a": {"a": 1}})
        with self.assertRaises(ValueError):
            direct_matrix(["a", "b"], {"a": {"z": 1}})

    def test_non_convergent_matrix_is_rejected(self):
        # every row and column sums to s, so X has spectral radius 1
        with self.assertRaises(ValueError):
            total_relation(np.array([[0.0, 1.0], [1.0, 0.0]]))

    def test_pairwise_strength_is_symmetric_and_scaled(self):
        result = run_dematel()
        strength = pairwise_strength(result["dimension_order"], result["total_relation_matrix"])
        self.assertEqual(len(strength), 28)
        self.assertAlmostEqual(max(strength.values()), 1.0)
        self.assertTrue(all(0 <= v <= 1 for v in strength.values()))
        order = result["dimension_order"]
        t = np.array(result["total_relation_matrix"])
        two_way = {(order[i], order[j]): t[i, j] + t[j, i] for i in range(8) for j in range(i + 1, 8)}
        self.assertEqual(max(strength, key=strength.get), max(two_way, key=two_way.get))
        # transport <-> workforce (0.306 + 0.250) outranks the one-way climate -> water link (0.527)
        self.assertEqual(set(max(strength, key=strength.get)), {"transportation", "workforce_community"})


if __name__ == "__main__":
    unittest.main()
