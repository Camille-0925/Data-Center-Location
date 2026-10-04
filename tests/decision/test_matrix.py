from __future__ import annotations

from copy import deepcopy
import unittest

from dc_locator.decision import ContractError, compare_runs, recommend, run_decision

from .builders import DIMENSIONS, add_passing_evidence, build_request, set_score, set_weights


def call_recommend(request):
    return recommend(
        request["dimension_scores"],
        request["scoring_config"],
        request["context"],
        project_profile=request["project_profile"],
        constraint_rules=request["constraint_rules"],
        evidence_records=request["evidence_records"],
    )


def by_id(result):
    return {item["candidate_id"]: item for item in result["recommendations"]["records"]}


class ScoringTests(unittest.TestCase):
    def test_equal_scores_give_40_and_contributions_sum_to_total(self):
        recommendation = call_recommend(build_request())["recommendations"]["records"][0]
        self.assertEqual(len(DIMENSIONS), 8)
        self.assertAlmostEqual(recommendation["score_0_100"], 40)
        self.assertEqual(len(recommendation["dimension_contributions"]), 8)
        self.assertAlmostEqual(sum(item["contribution_points"] for item in recommendation["dimension_contributions"]), 40)
        self.assertEqual(recommendation["eligibility_status"], "conditional")
        self.assertEqual(recommendation["rank"], 1)

    def test_weighted_sum_matches_hand_calculation(self):
        request = build_request()
        set_weights(request, water=0.30, climate_risk=0.20)  # other 6 dimensions get 0.50 / 6 each
        set_score(request, "51107", "water", 0.90)
        set_score(request, "51107", "climate_risk", 0.10)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        expected = 100 * (0.30 * 0.90 + 0.20 * 0.10 + 0.50 * 0.40)
        self.assertAlmostEqual(recommendation["score_0_100"], expected)

    def test_dynamic_weights_change_the_leader(self):
        request = build_request(("51107", "13121"))
        set_score(request, "51107", "water", 0.90)
        set_score(request, "13121", "fiber_connectivity", 0.90)
        water_first = deepcopy(request)
        set_weights(water_first, water=0.30, fiber_connectivity=0.05)
        fiber_first = deepcopy(request)
        set_weights(fiber_first, water=0.05, fiber_connectivity=0.30)
        leader = lambda req: next(i["candidate_id"] for i in call_recommend(req)["recommendations"]["records"] if i["rank"] == 1)
        self.assertEqual(leader(water_first), "51107")
        self.assertEqual(leader(fiber_first), "13121")

    def test_missing_dimension_makes_score_null(self):
        request = build_request()
        set_score(request, "51107", "water", None)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertIsNone(recommendation["score_0_100"])
        self.assertEqual(recommendation["eligibility_status"], "incomplete")
        self.assertIsNone(recommendation["rank"])
        self.assertEqual(recommendation["missing_dimension_ids"], ["water"])

    def test_real_zero_is_not_treated_as_missing(self):
        request = build_request()
        set_score(request, "51107", "energy_carbon", 0.0)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertEqual(recommendation["score_status"], "complete")
        self.assertAlmostEqual(recommendation["score_0_100"], 40 - 40 / 8)

    def test_zero_dimension_weight_is_allowed(self):
        request = build_request()
        set_weights(request, energy_carbon=0.0)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["score_0_100"], 40)

    def test_constant_dimension_is_reported(self):
        request = build_request(("51107", "51013"))
        set_score(request, "51107", "cooling_climate", 0.90)
        constant = [item for item in call_recommend(request)["diagnostics"] if "same score for every candidate" in item]
        self.assertTrue(any("energy_carbon" in item for item in constant))
        self.assertFalse(any("cooling_climate" in item for item in constant))

    def test_equal_scores_use_competition_ties(self):
        ranks = [item["rank"] for item in call_recommend(build_request(("51107", "51013", "13121")))["recommendations"]["records"]]
        self.assertEqual(ranks, [1, 1, 1])

    def test_pareto_uses_dimension_scores(self):
        request = build_request(("51107", "51013", "13121"))
        set_score(request, "51107", "water", 0.90)          # dominates 51013
        set_score(request, "13121", "fiber_connectivity", 0.90)
        set_score(request, "13121", "land_ecology", 0.10)   # better on one, worse on another
        statuses = {k: v["pareto_status"] for k, v in by_id(call_recommend(request)).items()}
        self.assertEqual(statuses, {"51107": "non_dominated", "51013": "dominated", "13121": "non_dominated"})

    def test_tradeoffs_compare_with_the_leader(self):
        request = build_request(("51107", "51013"))
        set_score(request, "51107", "water", 0.90)
        records = by_id(call_recommend(request))
        water = next(item for item in records["51013"]["tradeoffs"] if item["dimension_id"] == "water")
        self.assertEqual(water["comparison_candidate_id"], "51107")
        self.assertAlmostEqual(water["score_difference_current_minus_comparison"], -0.50)
        self.assertAlmostEqual(water["points_difference"], 100 * (1 / 8) * -0.50)

    def test_dimension_list_comes_from_config(self):
        request = build_request()
        request["scoring_config"]["dimension_order"] = ["water", "climate_risk", "transportation"]
        request["scoring_config"]["dimension_weights"] = {"water": 0.5, "climate_risk": 0.3, "transportation": 0.2}
        request["dimension_scores"]["records"][0]["scores"] = {"water": 1.0, "climate_risk": 0.5, "transportation": 0.0}
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["score_0_100"], 65)

    def test_real_run_rejects_test_only_config(self):
        result = call_recommend(build_request(run_mode="real", config_status="test_only"))
        recommendation = result["recommendations"]["records"][0]
        self.assertIsNone(recommendation["score_0_100"])
        self.assertEqual(recommendation["eligibility_status"], "incomplete")
        self.assertTrue(any("test_only" in item for item in result["diagnostics"]))


class ValidationTests(unittest.TestCase):
    def test_weights_must_sum_to_one(self):
        request = build_request()
        request["scoring_config"]["dimension_weights"]["water"] += 0.1
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_scores_must_be_between_0_and_1(self):
        request = build_request()
        set_score(request, "51107", "water", 1.2)
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_every_dimension_must_be_present(self):
        request = build_request()
        del request["dimension_scores"]["records"][0]["scores"]["water"]
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_duplicate_candidate_is_rejected(self):
        request = build_request()
        request["dimension_scores"]["records"].append(deepcopy(request["dimension_scores"]["records"][0]))
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_nonbaseline_scenario_is_rejected(self):
        request = build_request()
        request["context"]["scenario_id"] = "future"
        with self.assertRaises(ContractError):
            call_recommend(request)


class GateToggleTests(unittest.TestCase):
    def test_gates_disabled_ranks_without_profile_or_evidence(self):
        request = build_request(("51107", "51013"))
        set_score(request, "51107", "cooling_climate", 0.90)
        result = recommend(request["dimension_scores"], request["scoring_config"], request["context"])
        records = by_id(result)
        self.assertEqual(result["gate_results"]["records"], [])
        self.assertEqual(records["51107"]["rank"], 1)
        self.assertEqual(records["51013"]["rank"], 2)
        self.assertEqual(records["51107"]["gate_status"], "not_evaluated")
        self.assertEqual(records["51107"]["eligibility_status"], "conditional")
        self.assertTrue(any("gates are disabled" in item for item in result["diagnostics"]))

    def test_gates_enabled_false_flag(self):
        request = build_request(gates_enabled=False)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertEqual(recommendation["gate_status"], "not_evaluated")


class GateTests(unittest.TestCase):
    """Adelyn's original gate behaviour, unchanged when gates are enabled."""

    def test_120mw_fails_capacity_and_does_not_prove_delivery(self):
        request = build_request()
        add_passing_evidence(request, capacity=120)
        result = call_recommend(request)
        gates = {item["gate_id"]: item for item in result["gate_results"]["records"]}
        self.assertEqual(gates["power_capacity"]["status"], "fail")
        self.assertEqual(gates["delivery_date"]["status"], "unknown")
        self.assertEqual(result["recommendations"]["records"][0]["eligibility_status"], "excluded")
        self.assertAlmostEqual(result["recommendations"]["records"][0]["score_0_100"], 40)

    def test_exact_150mw_and_all_reviewed_gates_are_verified(self):
        request = build_request()
        add_passing_evidence(request, capacity=150)
        result = call_recommend(request)
        self.assertTrue(all(item["status"] == "pass" for item in result["gate_results"]["records"]))
        self.assertEqual(result["recommendations"]["records"][0]["eligibility_status"], "verified_feasible")

    def test_delivery_after_target_fails_independently(self):
        request = build_request()
        add_passing_evidence(request, capacity=150, delivery="2031-01-01")
        request["evidence_records"]["records"][0]["asserted_status"] = "unknown"
        gates = {item["gate_id"]: item for item in call_recommend(request)["gate_results"]["records"]}
        self.assertEqual(gates["power_capacity"]["status"], "pass")
        self.assertEqual(gates["delivery_date"]["status"], "fail")

    def test_all_failed_candidates_are_unranked(self):
        request = build_request(("51107", "51013"))
        for candidate_id in ("51107", "51013"):
            add_passing_evidence(request, candidate_id=candidate_id, capacity=120)
        recommendations = call_recommend(request)["recommendations"]["records"]
        self.assertTrue(all(item["eligibility_status"] == "excluded" for item in recommendations))
        self.assertTrue(all(item["rank"] is None for item in recommendations))

    def test_demo_evidence_is_ignored_in_real_run(self):
        request = build_request(run_mode="real")
        add_passing_evidence(request, is_demo=True)
        result = call_recommend(request)
        self.assertTrue(all(item["status"] == "unknown" for item in result["gate_results"]["records"]))
        self.assertTrue(any("demo evidence" in item for item in result["diagnostics"]))

    def test_two_scopes_are_not_combined(self):
        request = build_request()
        add_passing_evidence(request)
        second = deepcopy(request["evidence_records"]["records"][-1])
        second["evidence_id"] = "water_second_scope"
        second["assessment_scope_id"] = "another_scope"
        request["evidence_records"]["records"].append(second)
        result = call_recommend(request)
        self.assertTrue(all("multiple assessment scopes" in item["reason"] for item in result["gate_results"]["records"]))


class RunComparisonTests(unittest.TestCase):
    def test_compare_runs_reports_eligibility_change_without_score_change(self):
        before = call_recommend(build_request())
        after_request = build_request()
        after_request["context"]["run_id"] = "run_test_002"
        after_request["context"]["evidence_version"] = "2"
        for key in ["dimension_scores", "evidence_records"]:
            after_request[key]["context"] = deepcopy(after_request["context"])
        add_passing_evidence(after_request)
        changes = compare_runs(before, call_recommend(after_request))["records"][0]["changed_recommendations"][0]["changes"]
        self.assertIn("eligibility_status", changes)
        self.assertNotIn("score_0_100", changes)

    def test_compare_runs_reports_rank_change_from_new_weights(self):
        request = build_request(("51107", "13121"), gates_enabled=False)
        set_score(request, "51107", "water", 0.90)
        set_score(request, "13121", "fiber_connectivity", 0.90)
        first = deepcopy(request)
        set_weights(first, water=0.30, fiber_connectivity=0.05)
        second = deepcopy(request)
        set_weights(second, water=0.05, fiber_connectivity=0.30)
        second["context"]["run_id"] = "run_test_002"
        second["context"]["preference_profile_id"] = "fiber_first"
        second["scoring_config"]["preference_profile_id"] = "fiber_first"
        second["dimension_scores"]["context"] = deepcopy(second["context"])
        report = compare_runs(call_recommend(first), call_recommend(second))["records"][0]
        changed = {item["candidate_id"]: item["changes"] for item in report["changed_recommendations"]}
        self.assertIn("rank", changed["51107"])
        self.assertEqual(report["changed_inputs"][0]["field"], "preference_profile_id")

    def test_run_decision_accepts_precomputed_scores_or_a_callable(self):
        request = build_request()
        direct = run_decision(
            scoring_config=request["scoring_config"],
            context=request["context"],
            dimension_scores=request["dimension_scores"],
        )
        computed = run_decision(
            scoring_config=request["scoring_config"],
            context=request["context"],
            compute_dimension_scores_fn=lambda context: request["dimension_scores"],
        )
        self.assertEqual(direct["recommendations"]["records"], computed["recommendations"]["records"])


if __name__ == "__main__":
    unittest.main()
