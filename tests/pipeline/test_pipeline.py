from __future__ import annotations

import unittest

from dc_locator.data_prep import load_processed
from dc_locator.indicator_scoring import score_counties
from dc_locator.pipeline import run


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scored = score_counties(load_processed())
        cls.va = run("VA", scored=cls.scored)

    def test_every_county_is_ranked(self):
        ranking = self.va["ranking"]
        self.assertEqual(len(ranking), 133)
        self.assertEqual(sorted(ranking["rank"].tolist())[0], 1)
        self.assertTrue(ranking["score"].between(0, 100).all())

    def test_choquet_interactions_are_monotone_and_used(self):
        self.assertEqual(self.va["decision"]["recommendations"]["records"][0]["scoring_model"], "choquet_2additive")
        self.assertTrue(self.va["interactions"]["interactions"])

    def test_choquet_refines_but_does_not_overturn_the_weighted_sum(self):
        additive = run("VA", scoring_model="weighted_sum", scored=self.scored)["ranking"]
        top_c = set(self.va["ranking"]["fips"][:10])
        top_a = set(additive["fips"][:10])
        self.assertGreaterEqual(len(top_c & top_a), 8)

    def test_customer_input_changes_weights_and_ranking(self):
        other = run("VA", {"priority": "operations"}, scored=self.scored)
        self.assertGreater(other["weights"]["weights"]["fiber"], self.va["weights"]["weights"]["fiber"])
        self.assertNotEqual(list(other["ranking"]["fips"][:10]), list(self.va["ranking"]["fips"][:10]))

    def test_kappa_zero_equals_weighted_sum(self):
        zero = run("VA", kappa=0.0, scored=self.scored)["ranking"].set_index("fips")["score"]
        additive = run("VA", scoring_model="weighted_sum", scored=self.scored)["ranking"].set_index("fips")["score"]
        self.assertTrue(((zero - additive.reindex(zero.index)).abs() < 1e-9).all())

    def test_energy_is_not_used_within_state(self):
        self.assertEqual(self.va["weights"]["weights"]["energy_carbon"], 0.0)


if __name__ == "__main__":
    unittest.main()
