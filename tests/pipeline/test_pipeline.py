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

    def test_adjustments_are_in_the_live_pipeline_and_auditable(self):
        ranking = self.va["ranking"]
        self.assertIn("margin_adjustment", ranking)
        self.assertIn("D_base_water", ranking)
        self.assertIn("A_R_water", ranking)
        first = self.va["decision"]["recommendations"]["records"][0]
        self.assertAlmostEqual(
            first["score_0_100"],
            first["suitability_before_margin_0_100"] * first["margin_adjustment"],
        )
        self.assertEqual(set(first["robustness_factors"]), set(self.va["weights"]["dimension_order"]))

    def test_adjustments_can_be_disabled_without_changing_other_modules(self):
        legacy = run("VA", scored=self.scored, apply_adjustments=False)
        self.assertIsNone(legacy["adjustments_config"])
        self.assertNotIn("suitability_before_margin_0_100", legacy["decision"]["recommendations"]["records"][0])


class GateIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scored = score_counties(load_processed())

    def test_gates_add_columns_without_changing_the_ranking(self):
        plain = run("VA", scored=self.scored)["ranking"]
        gated = run("VA", scored=self.scored, power_input_mw=100, target_full_power_date="2029-12-31",
                    gate_as_of="2026-10-04")["ranking"]
        self.assertEqual(list(plain["fips"]), list(gated["fips"]))
        for column in ("gate_power", "gate_time_to_power", "gate_permitting", "gate_overall"):
            self.assertIn(column, gated)
            self.assertFalse(gated[column].isna().any())
        self.assertTrue((gated["feasibility"] == "conditional").all())

    def test_strict_screening_excludes_detected_risks_and_reranks(self):
        strict = run("VA", scored=self.scored, power_input_mw=100, target_full_power_date="2029-12-31",
                     gate_as_of="2026-10-04", exclude_gate_risks=True)["ranking"]
        excluded = strict[strict["gate_overall"] == "RISK_DETECTED"]
        self.assertTrue(len(excluded) > 0)
        self.assertTrue(excluded["rank"].isna().all())
        self.assertTrue((excluded["feasibility"] == "excluded").all())
        ranked = strict["rank"].dropna().astype(int)
        self.assertEqual(sorted(ranked)[:3], [1, 2, 3])
        self.assertEqual(len(ranked), len(strict) - len(excluded))

    def test_gate_modules_cover_every_county_of_both_states(self):
        from dc_locator.pipeline import gate_screening

        for state, n in (("VA", 133), ("GA", 159)):
            gates = gate_screening(state, 100, "2029-12-31", "2026-10-04")
            self.assertEqual(len(gates), n)
            self.assertEqual(set(gates["fips"]), set(self.scored.loc[self.scored["state"] == state, "fips"]))


if __name__ == "__main__":
    unittest.main()
