from __future__ import annotations

import random
import unittest

from dc_locator.decision import ContractError, recommend

from .builders import DIMENSIONS, build_request, set_score


def two_dimension_request(phi_water, phi_cooling, interaction, scores_by_id):
    request = build_request(tuple(scores_by_id), gates_enabled=False)
    config = request["scoring_config"]
    config["dimension_order"] = ["water", "cooling_climate"]
    config["dimension_weights"] = {"water": phi_water, "cooling_climate": phi_cooling}
    config["interactions"] = [{"dimensions": ["water", "cooling_climate"], "value": interaction}]
    for record in request["dimension_scores"]["records"]:
        water, cooling = scores_by_id[record["candidate_id"]]
        record["scores"] = {"water": water, "cooling_climate": cooling}
    return request


def run(request):
    result = recommend(request["dimension_scores"], request["scoring_config"], request["context"])
    return {item["candidate_id"]: item for item in result["recommendations"]["records"]}, result["diagnostics"]


def choquet_min_max_form(scores, phi, interactions):
    """Independent reference: Grabisch's min/max form of the 2-additive Choquet integral."""

    total = 0.0
    load = {d: 0.0 for d in phi}
    for (k, l), value in interactions.items():
        load[k] += abs(value) / 2
        load[l] += abs(value) / 2
        total += value * min(scores[k], scores[l]) if value > 0 else abs(value) * max(scores[k], scores[l])
    total += sum(scores[d] * (phi[d] - load[d]) for d in phi)
    return 100 * total


class ChoquetTests(unittest.TestCase):
    def test_complementarity_rewards_balance(self):
        records, _ = run(two_dimension_request(0.5, 0.5, 0.4, {"BAL": (0.5, 0.5), "IMB": (0.9, 0.1)}))
        self.assertAlmostEqual(records["BAL"]["score_0_100"], 50.0)
        self.assertAlmostEqual(records["IMB"]["score_0_100"], 100 * (0.5 - 0.5 * 0.4 * 0.8))  # 34
        self.assertEqual(records["BAL"]["rank"], 1)

    def test_redundancy_does_not_count_overlap_twice(self):
        records, _ = run(two_dimension_request(0.5, 0.5, -0.4, {"BAL": (0.5, 0.5), "IMB": (0.9, 0.1)}))
        self.assertAlmostEqual(records["IMB"]["score_0_100"], 66.0)
        self.assertEqual(records["IMB"]["rank"], 1)

    def test_without_interactions_equal_to_weighted_sum(self):
        records, _ = run(two_dimension_request(0.5, 0.5, 0.0, {"BAL": (0.5, 0.5), "IMB": (0.9, 0.1)}))
        self.assertAlmostEqual(records["IMB"]["score_0_100"], 50.0)
        self.assertEqual(records["IMB"]["scoring_model"], "weighted_sum")

    def test_matches_independent_min_max_form_on_eight_dimensions(self):
        rng = random.Random(7)
        phi = {d: 1 / 8 for d in DIMENSIONS}
        interactions = {
            ("water", "cooling_climate"): 0.10,
            ("fiber_connectivity", "workforce_community"): -0.08,
            ("transportation", "workforce_community"): -0.06,
            ("climate_risk", "water"): 0.05,
        }
        request = build_request(tuple(f"C{i}" for i in range(20)), gates_enabled=False)
        request["scoring_config"]["interactions"] = [{"dimensions": list(k), "value": v} for k, v in interactions.items()]
        for record in request["dimension_scores"]["records"]:
            record["scores"] = {d: rng.random() for d in DIMENSIONS}
        records, _ = run(request)
        for record in request["dimension_scores"]["records"]:
            expected = choquet_min_max_form(record["scores"], phi, interactions)
            self.assertAlmostEqual(records[record["candidate_id"]]["score_0_100"], expected)

    def test_contributions_add_up_to_score(self):
        records, _ = run(two_dimension_request(0.5, 0.5, 0.4, {"IMB": (0.9, 0.1)}))
        item = records["IMB"]
        parts = [c["contribution_points"] for c in item["dimension_contributions"] + item["interaction_contributions"]]
        self.assertAlmostEqual(sum(parts), item["score_0_100"])
        self.assertEqual(item["interaction_contributions"][0]["type"], "complementarity")
        self.assertEqual(item["scoring_model"], "choquet_2additive")

    def test_bounds_all_zero_and_all_one(self):
        records, _ = run(two_dimension_request(0.5, 0.5, 0.8, {"ZERO": (0.0, 0.0), "ONE": (1.0, 1.0)}))
        self.assertAlmostEqual(records["ZERO"]["score_0_100"], 0.0)
        self.assertAlmostEqual(records["ONE"]["score_0_100"], 100.0)

    def test_monotonicity_condition_is_enforced(self):
        with self.assertRaises(ContractError):
            run(two_dimension_request(0.5, 0.5, 1.01, {"A": (0.5, 0.5)}))  # interaction value out of range
        request = two_dimension_request(0.3, 0.7, 0.8, {"A": (0.5, 0.5)})  # water: 0.3 < 0.8 / 2
        with self.assertRaises(ContractError):
            run(request)

    def test_score_never_decreases_when_a_dimension_improves(self):
        rng = random.Random(11)
        phi = {d: 1 / 8 for d in DIMENSIONS}
        interactions = [
            {"dimensions": ["water", "cooling_climate"], "value": 0.12},
            {"dimensions": ["fiber_connectivity", "workforce_community"], "value": -0.12},
            {"dimensions": ["climate_risk", "water"], "value": 0.12},
        ]
        for _ in range(200):
            base = {d: rng.random() for d in DIMENSIONS}
            dim = rng.choice(DIMENSIONS)
            better = dict(base, **{dim: min(1.0, base[dim] + rng.random() * 0.5)})
            request = build_request(("LO", "HI"), gates_enabled=False)
            request["scoring_config"]["dimension_weights"] = phi
            request["scoring_config"]["interactions"] = interactions
            request["dimension_scores"]["records"][0]["scores"] = base
            request["dimension_scores"]["records"][1]["scores"] = better
            records, _ = run(request)
            self.assertGreaterEqual(records["HI"]["score_0_100"] + 1e-9, records["LO"]["score_0_100"])

    def test_invalid_interaction_entries_are_rejected(self):
        for bad in (
            [{"dimensions": ["water", "water"], "value": 0.1}],
            [{"dimensions": ["water", "heat_reuse"], "value": 0.1}],
            [{"dimensions": ["water", "cooling_climate"], "value": 0.1},
             {"dimensions": ["cooling_climate", "water"], "value": 0.1}],
        ):
            request = build_request(gates_enabled=False)
            request["scoring_config"]["interactions"] = bad
            with self.assertRaises(ContractError):
                run(request)

    def test_constant_dimension_with_interactions_is_reported_differently(self):
        request = build_request(("A", "B"), gates_enabled=False)
        set_score(request, "A", "water", 0.9)
        request["scoring_config"]["interactions"] = [{"dimensions": ["water", "energy_carbon"], "value": 0.1}]
        _, diagnostics = run(request)
        self.assertTrue(any("energy_carbon" in d and "interaction" in d for d in diagnostics))


if __name__ == "__main__":
    unittest.main()
