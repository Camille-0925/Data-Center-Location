from __future__ import annotations

from copy import deepcopy
import unittest

from dc_locator.decision import ContractError, compare_runs, recommend, run_decision

from .builders import DIMENSIONS, METRICS, add_passing_evidence, build_request, set_indicator_score


def call_recommend(request):
    return recommend(
        request["metric_results"],
        request["indicator_scores"],
        request["dimension_scores"],
        request["scoring_config"],
        request["project_profile"],
        request["constraint_rules"],
        request["evidence_records"],
        request["context"],
    )


class ScoringTests(unittest.TestCase):
    def test_eight_dimensions_eighteen_metrics_score_40(self):
        request = build_request()
        result = call_recommend(request)
        recommendation = result["recommendations"]["records"][0]
        self.assertEqual(len(DIMENSIONS), 8)
        self.assertEqual(len(METRICS), 18)
        self.assertAlmostEqual(recommendation["score_0_100"], 40)
        self.assertEqual(len(recommendation["metric_contributions"]), 18)
        self.assertAlmostEqual(
            sum(item["contribution_points"] for item in recommendation["metric_contributions"]),
            40,
        )
        self.assertEqual(recommendation["eligibility_status"], "conditional")
        self.assertEqual(recommendation["rank"], 1)

    def test_local_weights_inside_dimension_are_applied(self):
        request = build_request()
        set_indicator_score(request, "51107", "low_impervious_share", 100)
        result = call_recommend(request)
        recommendation = result["recommendations"]["records"][0]
        # land_ecology moves from 0.40 to (100+40+40)/300 = 0.60; dimension weight 1/8.
        self.assertAlmostEqual(recommendation["score_0_100"], 40 + 100 * (0.60 - 0.40) / 8)
        contribution = next(
            item for item in recommendation["metric_contributions"] if item["metric_id"] == "low_impervious_share"
        )
        self.assertAlmostEqual(contribution["global_leaf_weight"], (1 / 8) * (1 / 3))

    def test_dynamic_dimension_weights_change_ranking(self):
        request = build_request(("51107", "13121"))
        set_indicator_score(request, "51107", "baseline_water_stress", 100)
        set_indicator_score(request, "51107", "future_water_stress_2050", 100)
        set_indicator_score(request, "13121", "commercial_fiber_100_20_share", 100)
        set_indicator_score(request, "13121", "commercial_fiber_1000_100_share", 100)
        weights = request["scoring_config"]["dimension_weights"]

        water_heavy = deepcopy(request)
        water_heavy["scoring_config"]["dimension_weights"] = {**weights, "water": 0.3, "fiber_connectivity": 0.05, "land_ecology": 0.025}
        fiber_heavy = deepcopy(request)
        fiber_heavy["scoring_config"]["dimension_weights"] = {**weights, "water": 0.05, "fiber_connectivity": 0.3, "land_ecology": 0.025}

        def leader(req):
            records = call_recommend(req)["recommendations"]["records"]
            return next(item["candidate_id"] for item in records if item["rank"] == 1)

        self.assertEqual(leader(water_heavy), "51107")
        self.assertEqual(leader(fiber_heavy), "13121")

    def test_missing_indicator_makes_score_null(self):
        request = build_request()
        record = request["dimension_scores"]["records"][0]
        record["scores"]["water"] = None
        record["score_status"] = "incomplete"
        record["missing_metric_ids"] = ["baseline_water_stress"]
        indicator = next(
            item for item in request["indicator_scores"]["records"] if item["metric_id"] == "baseline_water_stress"
        )
        indicator["score_0_100"] = None
        indicator["score_status"] = "incomplete"
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertIsNone(recommendation["score_0_100"])
        self.assertEqual(recommendation["eligibility_status"], "incomplete")
        self.assertIsNone(recommendation["rank"])
        self.assertIn("future_water_stress_2050", recommendation["missing_metric_ids"])

    def test_zero_dimension_weight_is_allowed(self):
        request = build_request()
        weights = request["scoring_config"]["dimension_weights"]
        weights["energy_carbon"] = 0.0
        for dimension_id in DIMENSIONS[:-1]:
            weights[dimension_id] = 1 / 7
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["score_0_100"], 40)

    def test_constant_dimension_is_reported(self):
        request = build_request(("51107", "51013"))
        set_indicator_score(request, "51107", "cdd65", 90)
        result = call_recommend(request)
        constant = [item for item in result["diagnostics"] if "same score for every candidate" in item]
        self.assertTrue(any("energy_carbon" in item for item in constant))
        self.assertFalse(any("cooling_climate" in item for item in constant))

    def test_local_weights_must_sum_to_one(self):
        request = build_request()
        request["scoring_config"]["indicators"][0]["local_weight"] = 0.9
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_dimension_without_indicator_is_rejected(self):
        request = build_request()
        request["scoring_config"]["indicators"] = [
            item for item in request["scoring_config"]["indicators"] if item["dimension_id"] != "transportation"
        ]
        request["scoring_config"]["required_score_metrics"] = [
            item["metric_id"] for item in request["scoring_config"]["indicators"]
        ]
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_real_zero_is_not_treated_as_missing(self):
        request = build_request()
        for key in ["metric_results", "indicator_scores"]:
            record = next(item for item in request[key]["records"] if item["metric_id"] == "grid_co2e_intensity")
            record["value" if key == "metric_results" else "raw_value"] = 0.0
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertEqual(recommendation["score_status"], "complete")

    def test_equal_scores_use_competition_ties(self):
        request = build_request(("51107", "51013", "13121"))
        ranks = [item["rank"] for item in call_recommend(request)["recommendations"]["records"]]
        self.assertEqual(ranks, [1, 1, 1])

    def test_omitted_missing_row_is_a_contract_error(self):
        request = build_request()
        request["metric_results"]["records"] = [
            item for item in request["metric_results"]["records"] if item["metric_id"] != "baseline_water_stress"
        ]
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_real_run_rejects_test_only_score_for_completion(self):
        request = build_request(run_mode="real", config_status="test_only")
        result = call_recommend(request)
        recommendation = result["recommendations"]["records"][0]
        self.assertIsNone(recommendation["score_0_100"])
        self.assertEqual(recommendation["eligibility_status"], "incomplete")
        self.assertTrue(any("test_only" in item for item in result["diagnostics"]))

    def test_pareto_uses_raw_directions(self):
        request = build_request(("51107", "51013"))
        directions = {item["metric_id"]: item["direction"] for item in request["scoring_config"]["indicators"]}
        for record in request["metric_results"]["records"]:
            if record["candidate_id"] == "51107":
                record["value"] = 0.0 if directions[record["metric_id"]] == "low_better" else 10.0
            else:
                record["value"] = 1.0 if directions[record["metric_id"]] == "low_better" else 9.0
            matching = next(
                item
                for item in request["indicator_scores"]["records"]
                if item["candidate_id"] == record["candidate_id"] and item["metric_id"] == record["metric_id"]
            )
            matching["raw_value"] = record["value"]
        statuses = {
            item["candidate_id"]: item["pareto_status"]
            for item in call_recommend(request)["recommendations"]["records"]
        }
        self.assertEqual(statuses["51107"], "non_dominated")
        self.assertEqual(statuses["51013"], "dominated")

    def test_nonbaseline_scenario_is_rejected(self):
        request = build_request()
        request["context"]["scenario_id"] = "future"
        with self.assertRaises(ContractError):
            call_recommend(request)


def use_aggregation(request, dimension_id, method, local_weights=None):
    """Switch one dimension's aggregation (and optionally its local weights) in the config."""

    request["scoring_config"].setdefault("dimension_aggregation", {})[dimension_id] = method
    if local_weights:
        for item in request["scoring_config"]["indicators"]:
            if item["metric_id"] in local_weights:
                item["local_weight"] = local_weights[item["metric_id"]]


class AggregationTests(unittest.TestCase):
    def test_geometric_mean_for_climate(self):
        request = build_request()
        use_aggregation(request, "climate_risk", "weighted_geometric")
        set_indicator_score(request, "51107", "wildfire_bp_national_pct", 90)
        set_indicator_score(request, "51107", "inland_flood_eal_national_pct", 10)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["dimension_scores"]["climate_risk"], 0.30)
        # An arithmetic mean would give 0.50; the geometric mean penalizes the poor flood score.
        self.assertAlmostEqual(recommendation["score_0_100"], 40 + 100 * (0.30 - 0.40) / 8)
        climate = [item for item in recommendation["metric_contributions"] if item["dimension_id"] == "climate_risk"]
        self.assertTrue(all(item["contribution_points"] is None for item in climate))

    def test_min_for_water(self):
        request = build_request()
        use_aggregation(request, "water", "min")
        set_indicator_score(request, "51107", "baseline_water_stress", 90)
        set_indicator_score(request, "51107", "future_water_stress_2050", 20)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["dimension_scores"]["water"], 0.20)
        self.assertAlmostEqual(recommendation["score_0_100"], 40 + 100 * (0.20 - 0.40) / 8)

    def test_weighted_geometric_land_uses_local_weights(self):
        request = build_request()
        use_aggregation(
            request,
            "land_ecology",
            "weighted_geometric",
            {"low_impervious_share": 0.5, "protected_gap12_share": 0.25, "wetland_share": 0.25},
        )
        set_indicator_score(request, "51107", "low_impervious_share", 100)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["dimension_scores"]["land_ecology"], 1.0**0.5 * 0.4**0.25 * 0.4**0.25)

    def test_equal_utilities_give_same_score_for_every_method(self):
        request = build_request()
        use_aggregation(request, "climate_risk", "weighted_geometric")
        use_aggregation(request, "water", "min")
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        self.assertAlmostEqual(recommendation["score_0_100"], 40)

    def test_dimension_contributions_sum_to_total(self):
        request = build_request()
        use_aggregation(request, "climate_risk", "weighted_geometric")
        use_aggregation(request, "water", "min")
        set_indicator_score(request, "51107", "wildfire_bp_national_pct", 80)
        set_indicator_score(request, "51107", "future_water_stress_2050", 15)
        set_indicator_score(request, "51107", "interstate_distance_km", 95)
        recommendation = call_recommend(request)["recommendations"]["records"][0]
        points = [item["contribution_points"] for item in recommendation["dimension_contributions"]]
        self.assertEqual(len(points), 8)
        self.assertAlmostEqual(sum(points), recommendation["score_0_100"])
        transport = [item for item in recommendation["metric_contributions"] if item["dimension_id"] == "transportation"]
        transport_dimension = next(
            item for item in recommendation["dimension_contributions"] if item["dimension_id"] == "transportation"
        )
        self.assertAlmostEqual(sum(item["contribution_points"] for item in transport), transport_dimension["contribution_points"])

    def test_dimension_score_that_ignores_declared_aggregation_is_rejected(self):
        request = build_request()
        set_indicator_score(request, "51107", "wildfire_bp_national_pct", 90)
        set_indicator_score(request, "51107", "inland_flood_eal_national_pct", 10)
        # Dimension score was computed as an arithmetic mean (0.50); the config now says geometric.
        use_aggregation(request, "climate_risk", "weighted_geometric")
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_unknown_aggregation_is_rejected(self):
        request = build_request()
        use_aggregation(request, "water", "median")
        with self.assertRaises(ContractError):
            call_recommend(request)

    def test_aggregation_for_unknown_dimension_is_rejected(self):
        request = build_request()
        use_aggregation(request, "heat_reuse", "min")
        with self.assertRaises(ContractError):
            call_recommend(request)


class GateToggleTests(unittest.TestCase):
    def test_gates_disabled_ranks_without_profile_or_evidence(self):
        request = build_request(("51107", "51013"), gates_enabled=False)
        set_indicator_score(request, "51107", "cdd65", 90)
        result = recommend(
            request["metric_results"],
            request["indicator_scores"],
            request["dimension_scores"],
            request["scoring_config"],
            None,
            {"gates_enabled": False},
            None,
            request["context"],
        )
        records = {item["candidate_id"]: item for item in result["recommendations"]["records"]}
        self.assertEqual(result["gate_results"]["records"], [])
        self.assertEqual(records["51107"]["rank"], 1)
        self.assertEqual(records["51013"]["rank"], 2)
        self.assertEqual(records["51107"]["gate_status"], "not_evaluated")
        self.assertEqual(records["51107"]["eligibility_status"], "conditional")
        self.assertTrue(any("gates are disabled" in item for item in result["diagnostics"]))

    def test_missing_constraint_rules_means_gates_disabled(self):
        request = build_request(gates_enabled=False)
        result = recommend(
            request["metric_results"],
            request["indicator_scores"],
            request["dimension_scores"],
            request["scoring_config"],
            None,
            None,
            None,
            request["context"],
        )
        self.assertEqual(result["recommendations"]["records"][0]["gate_status"], "not_evaluated")


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
        gates = result["gate_results"]["records"]
        self.assertTrue(all(item["status"] == "pass" for item in gates))
        self.assertTrue(all(item["verification_status"] == "reviewed" for item in gates))
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
        self.assertTrue(all(item["status"] == "unknown" for item in result["gate_results"]["records"]))
        self.assertTrue(all("multiple assessment scopes" in item["reason"] for item in result["gate_results"]["records"]))


class RunComparisonTests(unittest.TestCase):
    def test_compare_runs_reports_eligibility_change_without_score_change(self):
        before = call_recommend(build_request())
        after_request = build_request()
        after_request["context"]["run_id"] = "run_test_002"
        after_request["context"]["evidence_version"] = "2"
        for key in ["metric_results", "indicator_scores", "dimension_scores", "evidence_records"]:
            after_request[key]["context"] = deepcopy(after_request["context"])
        add_passing_evidence(after_request)
        after = call_recommend(after_request)
        changes = compare_runs(before, after)["records"][0]["changed_recommendations"][0]["changes"]
        self.assertIn("eligibility_status", changes)
        self.assertNotIn("score_0_100", changes)

    def test_compare_runs_reports_rank_change_from_new_weights(self):
        request = build_request(("51107", "13121"), gates_enabled=False)
        set_indicator_score(request, "51107", "baseline_water_stress", 100)
        set_indicator_score(request, "13121", "commercial_fiber_1000_100_share", 100)
        weights = request["scoring_config"]["dimension_weights"]
        first = deepcopy(request)
        first["scoring_config"]["dimension_weights"] = {**weights, "water": 0.3, "fiber_connectivity": 0.05, "land_ecology": 0.025}
        second = deepcopy(request)
        second["context"]["run_id"] = "run_test_002"
        second["context"]["preference_profile_id"] = "fiber_first"
        second["scoring_config"]["preference_profile_id"] = "fiber_first"
        second["scoring_config"]["dimension_weights"] = {**weights, "water": 0.05, "fiber_connectivity": 0.3, "land_ecology": 0.025}
        for key in ["metric_results", "indicator_scores", "dimension_scores", "evidence_records"]:
            second[key]["context"] = deepcopy(second["context"])
        report = compare_runs(call_recommend(first), call_recommend(second))["records"][0]
        changed = {item["candidate_id"]: item["changes"] for item in report["changed_recommendations"]}
        self.assertIn("rank", changed["51107"])
        self.assertEqual(report["changed_inputs"][0]["field"], "preference_profile_id")

    def test_run_decision_accepts_precomputed_upstream_outputs(self):
        request = build_request()
        result = run_decision(
            project_profile=request["project_profile"],
            candidates=None,
            feature_inputs=None,
            scenario_config={"scenario_id": "baseline"},
            scoring_config=request["scoring_config"],
            constraint_rules=request["constraint_rules"],
            evidence_records=request["evidence_records"],
            context=request["context"],
            metric_results=request["metric_results"],
            indicator_scores=request["indicator_scores"],
            dimension_scores=request["dimension_scores"],
        )
        self.assertEqual(len(result["recommendations"]["records"]), 1)


if __name__ == "__main__":
    unittest.main()
