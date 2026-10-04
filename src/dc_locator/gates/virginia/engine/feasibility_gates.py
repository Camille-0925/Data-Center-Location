"""Site-level feasibility gates. Standard library only; no UI or data fetching.

API: evaluate_bundle(payload, as_of="YYYY-MM-DD") -> JSON-compatible dict.
CLI: python feasibility_gates.py input.json --as-of 2026-10-03 --output result.json
Evidence must already have been extracted and reviewed. This module does not
verify source authenticity, perform power-flow studies, or interpret ordinances.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

RULE_VERSION = "1.0"
GATES = ("power_availability", "time_to_power", "permitting_zoning")
POWER_CLAIMS = {"deliverable_capacity", "capacity_limit", "capacity_delivery"}
PERMIT_LEVELS = {"project_confirmation", "public_planning"}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def _date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _profile(request):
    """Normalize demand without inventing missing engineering assumptions."""
    missing_power, missing_time = [], []
    basis, mw = request.get("power_input_basis"), _number(request.get("power_input_mw"))
    if basis not in {"facility", "it"}:
        missing_power.append("power_input_basis")
    if mw is None:
        missing_power.append("power_input_mw")
    required = mw
    if basis == "it":
        pue = _number(request.get("design_pue"))
        if pue is None or pue < 1:
            missing_power.append("design_pue")
            required = None
        elif mw is not None:
            required = mw * pue
            if not math.isfinite(required):
                missing_power.append("power_input_mw/design_pue overflow")
                required = None
    if basis not in {"facility", "it"}:
        required = None
    project_type = request.get("project_type")
    if project_type not in {"new_build", "expansion"}:
        missing_power.append("project_type")
    if project_type == "expansion" and request.get("expansion_capacity_basis") != "additional":
        missing_power.append("expansion_capacity_basis=additional")
    target = _date(request.get("target_full_power_date"))
    if target is None:
        missing_time.append("target_full_power_date")
    phases = request.get("power_milestones", [])
    if not isinstance(phases, list):
        missing_power.append("power_milestones must be a list")
        phases = []
    milestones = []
    for phase in phases:
        if not isinstance(phase, dict):
            missing_power.append("invalid power_milestone")
            continue
        p_mw, p_date = _number(phase.get("facility_mw")), _date(phase.get("date"))
        if p_mw is None or p_date is None:
            missing_power.append("milestone facility_mw/date")
        else:
            milestones.append((p_date, p_mw))
    milestones.sort()
    previous = 0
    for p_date, p_mw in milestones:
        if p_mw < previous or (required is not None and p_mw > required) or (target and p_date > target):
            missing_power.append("power_milestones contradict full-capacity requirement")
        previous = p_mw
    if required is not None and target is not None:
        milestones.append((target, required))
    milestones = sorted(set(milestones))
    return required, milestones, sorted(set(missing_power)), sorted(set(missing_time))


def _issue(e, as_of, levels):
    if e.get("verification_status") != "verified":
        return "evidence_not_verified"
    if e.get("evidence_level") not in levels:
        return "evidence_is_estimate_or_proxy"
    if e.get("geographic_scope") not in {"site", "project"}:
        return "evidence_not_site_specific"
    if not (e.get("source_url") or e.get("local_file")):
        return "source_reference_missing"
    if not e.get("source_locator"):
        return "source_locator_missing"
    for field in ("effective_from", "effective_until"):
        if e.get(field) is not None and _date(e[field]) is None:
            return "invalid_effective_date"
    if (_date(e.get("effective_from")) and _date(e.get("effective_until"))
            and _date(e["effective_from"]) > _date(e["effective_until"])):
        return "invalid_effective_interval"
    if _date(e.get("effective_from")) and _date(e["effective_from"]) > as_of:
        return "evidence_not_yet_effective"
    if _date(e.get("effective_until")) and _date(e["effective_until"]) < as_of:
        return "evidence_expired"
    if e.get("conditions_verification") not in {"satisfied", "not_applicable"}:
        return "conditions_not_verified"
    if e.get("conditions") and e.get("conditions_verification") == "not_applicable":
        return "conditions_require_verification"
    return None


def _result(gate, status, code, reason, evidence=(), missing=(), next_action="", **extra):
    return dict(gate_id=gate, status=status, input_status="READY", reason_code=code,
                reason=reason, used_evidence_ids=sorted(set(evidence)),
                missing_inputs=[], missing_evidence=list(missing),
                next_action=next_action, **extra)


def _input_result(gate, fields):
    out = _result(gate, None, "INPUT_REQUIRED", "先补充或修正项目需求。")
    out.update(input_status="INPUT_REQUIRED", missing_inputs=fields)
    return out


def _capacity(e):
    field = "capacity_at_date_mw" if e.get("claim_type") == "capacity_delivery" else "capacity_mw"
    value = e.get(field)
    if (e.get("capacity_basis") != "facility" or isinstance(value, bool)
            or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
        return None
    return float(value)


def _power_results(request, site, plan, evidence, as_of):
    required, milestones, p_missing, t_missing = _profile(request)
    relevant = [e for e in evidence if e.get("site_id") == site["site_id"]
                and plan is not None and e.get("power_plan_id") == plan["power_plan_id"]
                and e.get("gate_id") in GATES[:2] and e.get("claim_type") in POWER_CLAIMS]
    valid, rejected = [], []
    for e in relevant:
        issue = _issue(e, as_of, {"project_confirmation"})
        if not issue and _capacity(e) is None:
            issue = "capacity_or_basis_invalid"
        (rejected if issue else valid).append((e, issue) if issue else e)
    live = [e for e in relevant if e.get("verification_status") not in {"superseded", "expired"}
            and not (_date(e.get("effective_until")) and _date(e["effective_until"]) < as_of)]
    explicit_conflict = any(e.get("verification_status") == "conflicting" for e in live)
    capacities = [e for e in valid if e["claim_type"] != "capacity_limit"]
    limits = [e for e in valid if e["claim_type"] == "capacity_limit"]
    contradictory = capacities and limits and max(map(_capacity, capacities)) > min(map(_capacity, limits))
    blocked = explicit_conflict or contradictory
    reasons = sorted({issue for _, issue in rejected})
    if site.get("site_resolution_status") != "confirmed" or plan is None:
        reasons.append("confirmed_site_or_power_plan_missing")
        valid, capacities, limits = [], [], []
    action = "向 utility 核实同一站点和供电方案的设施 MW、分期交付日期及条件。"
    if p_missing:
        power = _input_result(GATES[0], p_missing)
    elif blocked:
        power = _result(GATES[0], "UNKNOWN", "CONFLICTING_EVIDENCE", "容量证据存在冲突，需要核实。", next_action=action)
    elif limits and min(map(_capacity, limits)) < required:
        power = _result(GATES[0], "FAIL", "CONFIRMED_CAPACITY_LIMIT", "已确认的方案容量上限低于项目需求。",
                        [e["evidence_id"] for e in limits], next_action="评估另一供电方案或修改容量需求。")
    elif capacities and max(map(_capacity, capacities)) >= required:
        chosen = [e for e in capacities if _capacity(e) >= required]
        power = _result(GATES[0], "PASS", "CAPACITY_SUPPORTED", "项目级证据支持所需设施容量；交付时间由下一 gate 检查。",
                        [e["evidence_id"] for e in chosen])
    else:
        power = _result(GATES[0], "UNKNOWN", "CAPACITY_UNCONFIRMED", "尚未确认所需容量；已有负荷或初期容量不能替代最终容量。",
                        missing=reasons or ["required_capacity_confirmation"], next_action=action)
    power["requirement_summary"] = {"required_facility_mw": required}
    power["observed_summary"] = {"supported_capacity_mw": max(map(_capacity, capacities), default=None),
                                 "capacity_limit_mw": min(map(_capacity, limits), default=None)}

    if p_missing or t_missing:
        timing = _input_result(GATES[1], sorted(set(p_missing + t_missing)))
    elif blocked:
        timing = _result(GATES[1], "UNKNOWN", "CONFLICTING_EVIDENCE", "同一方案证据存在冲突，需要核实。", next_action=action)
    else:
        checks = []
        for deadline, mw in milestones:
            rows, ambiguous_ids = [], []
            for e in valid:
                if e["claim_type"] != "capacity_delivery" or _capacity(e) < mw:
                    continue
                if e.get("date_type") != "project_capacity_delivery":
                    ambiguous_ids.append(e["evidence_id"])
                    continue
                start, end = _date(e.get("delivery_date_start")), _date(e.get("delivery_date_end"))
                if not start or not end or start > end:
                    ambiguous_ids.append(e["evidence_id"])
                else:
                    rows.append((start, end, e["evidence_id"]))
            on_time = [r for r in rows if r[1] <= deadline]
            uncertain = [r for r in rows if r[0] <= deadline < r[1]]
            if on_time:
                status, used = "PASS", [r[2] for r in on_time]
            elif uncertain or ambiguous_ids or not rows:
                status, used = "UNKNOWN", [r[2] for r in uncertain]
            else:
                status, used = "FAIL", [r[2] for r in rows]
            checks.append(dict(required_facility_mw=mw, deadline=deadline.isoformat(), status=status, evidence_ids=used))
        status = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "UNKNOWN" if any(c["status"] == "UNKNOWN" for c in checks) else "PASS"
        timing = _result(GATES[1], status,
                         {"PASS":"DELIVERY_SUPPORTED", "FAIL":"DELIVERY_AFTER_TARGET", "UNKNOWN":"DELIVERY_UNCONFIRMED"}[status],
                         {"PASS":"同一方案的各阶段容量交付日期满足需求。", "FAIL":"当前确认方案至少一个阶段的交付日期晚于目标。", "UNKNOWN":"缺少与所需容量对应的确定交付时间，或时间区间跨越目标。"}[status],
                         [eid for c in checks for eid in c["evidence_ids"]],
                         missing=(reasons or ["capacity_specific_delivery_schedule"]) if status == "UNKNOWN" else [],
                         next_action=action if status != "PASS" else "", milestone_results=checks)
    timing["requirement_summary"] = [{"date":dt.isoformat(),"facility_mw":mw} for dt,mw in milestones]
    timing["observed_summary"] = timing.get("milestone_results", [])
    return power, timing


def _permit_result(request, site, evidence, checks, as_of):
    gate = GATES[2]
    scope = request.get("assessment_scope", "land_use_diligence")
    if scope not in {"land_use_diligence", "construction_ready"}:
        return _input_result(gate, ["assessment_scope"])
    action = "核实本地块当前适用的规则、必要批准清单和未满足条件。"
    index = {e["evidence_id"]:e for e in evidence}
    rows = [c for c in checks if c.get("site_id") == site["site_id"]
            and c.get("request_version") == request.get("request_version",1)
            and c.get("assessment_scope") == scope]
    def usable(ids, requirement=False):
        return bool(ids) and all(eid in index and index[eid].get("site_id") == site["site_id"]
            and index[eid].get("gate_id") == gate
            and index[eid].get("claim_type") in ({"permit_requirement"} if requirement else {"permit_status","zoning_permission"})
            and _issue(index[eid], as_of, PERMIT_LEVELS) is None for eid in ids)
    outcomes, used = [], []
    for c in rows:
        requirement_ok = usable(c.get("requirement_evidence_ids",[]), requirement=True)
        app = c.get("applicability")
        if c.get("conditions") and c.get("conditions_verification") != "satisfied":
            outcomes.append("UNKNOWN")
            continue
        if requirement_ok and app == "not_applicable":
            outcomes.append("NOT_APPLICABLE")
            used.extend(c["requirement_evidence_ids"])
        elif requirement_ok and app == "required" and usable(c.get("supporting_evidence_ids",[])):
            outcome = {"satisfied":"PASS", "unsatisfied":"FAIL"}.get(c.get("status"),"UNKNOWN")
            outcomes.append(outcome)
            used.extend(c["requirement_evidence_ids"] + c["supporting_evidence_ids"])
        else:
            outcomes.append("UNKNOWN")
    if site.get("site_resolution_status") != "confirmed":
        status = "UNKNOWN"
    elif "FAIL" in outcomes:
        status = "FAIL"
    elif (not rows or site.get("permit_checklist_confirmed") is not True
          or site.get("permit_checklist_scope") != scope
          or "UNKNOWN" in outcomes or not any(o=="PASS" for o in outcomes)):
        status = "UNKNOWN"
    else:
        status = "PASS"
    return _result(gate,status,
        {"PASS":"PERMITS_SUPPORTED_WITHIN_SCOPE", "FAIL":"PERMIT_REQUIREMENT_UNSATISFIED", "UNKNOWN":"PERMIT_EVIDENCE_INCOMPLETE"}[status],
        {"PASS":"当前评估范围的必要许可检查有证据支持；不等于全部施工许可齐全。", "FAIL":"当前评估范围内至少一个必要条件有证据证明不满足。", "UNKNOWN":"适用许可清单、批准或条件尚未完整核实。"}[status], used,
        missing=["site_specific_complete_permit_checks"] if status=="UNKNOWN" else [],
        next_action=action if status!="PASS" else "", assessment_scope=scope,
        observed_summary=[dict(check_id=c.get("check_id"),status=o) for c,o in zip(rows,outcomes)],
        requirement_summary={"assessment_scope":scope})


def evaluate_bundle(payload: dict, as_of: str | None = None) -> dict:
    """Evaluate each site / power plan independently; never infer county-wide PASS."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    today = _date(as_of) if as_of else date.today()
    if today is None:
        raise ValueError("as_of must be YYYY-MM-DD")
    request = payload.get("request")
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    arrays = {name:payload.get(name,[]) for name in ("sites","power_plans","evidence","permit_checks")}
    for name, rows in arrays.items():
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
            raise ValueError(name+" must be a list of objects")
        id_field = {"sites":"site_id","power_plans":"power_plan_id","evidence":"evidence_id","permit_checks":"check_id"}[name]
        ids = [row.get(id_field) for row in rows]
        if any(not isinstance(i,str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError(name+": missing or duplicate "+id_field)
    sites, plans, evidence, checks = (arrays[n] for n in ("sites","power_plans","evidence","permit_checks"))
    site_ids = {s["site_id"] for s in sites}
    for check in checks:
        for field in ("requirement_evidence_ids", "supporting_evidence_ids"):
            ids = check.get(field, [])
            if not isinstance(ids, list) or any(not isinstance(i,str) for i in ids):
                raise ValueError(field + " must be a list of evidence IDs")
    for p in plans:
        if p.get("site_id") not in site_ids:
            raise ValueError("power plan references an unknown site")
    results=[]
    for site in sites:
        fips=site.get("county_fips")
        if not isinstance(fips,str) or len(fips)!=5 or not fips.isdigit():
            raise ValueError("site county_fips must be a five-digit string")
        for plan in [p for p in plans if p["site_id"]==site["site_id"]] or [None]:
            power,timing = _power_results(request,site,plan,evidence,today)
            permit = _permit_result(request,site,evidence,checks,today)
            gates=[power,timing,permit]
            statuses=[g["status"] for g in gates]
            overall = ("INPUT_REQUIRED" if any(g["input_status"]=="INPUT_REQUIRED" for g in gates)
                       else "INFEASIBLE" if "FAIL" in statuses else "CONDITIONAL" if "UNKNOWN" in statuses
                       else "FEASIBLE_WITHIN_SCOPE")
            results.append(dict(request_id=request.get("request_id"),request_version=request.get("request_version",1),
                county_fips=fips,site_id=site["site_id"],power_plan_id=plan["power_plan_id"] if plan else None,
                overall_status=overall,assessment_scope=request.get("assessment_scope","land_use_diligence"),gates=gates))
    candidates = payload.get("candidate_county_fips", [])
    if not isinstance(candidates, list):
        raise ValueError("candidate_county_fips must be a list")
    for fips in candidates:
        if not isinstance(fips,str) or len(fips)!=5 or not fips.isdigit():
            raise ValueError("candidate_county_fips must contain five-digit strings")
    counties=sorted(set(candidates) | {s["county_fips"] for s in sites})
    return dict(rule_version=RULE_VERSION,evaluated_at=today.isoformat(),site_results=results,
        county_evidence_summary=[dict(county_fips=fips,
            site_plan_results=[dict(site_id=r["site_id"],power_plan_id=r["power_plan_id"],status=r["overall_status"]) for r in results if r["county_fips"]==fips],
            note="这里只汇总站点及方案证据，不判定整个 county 可行。") for fips in counties])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--as-of",help="Evidence validity date, YYYY-MM-DD")
    args=parser.parse_args()
    try:
        result=evaluate_bundle(json.loads(args.input.read_text(encoding="utf-8")),args.as_of)
    except (ValueError,OSError) as exc:
        parser.exit(2,"Input error: "+str(exc)+"\n")
    text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    if args.output:
        args.output.write_text(text,encoding="utf-8")
    else:
        print(text,end="")


if __name__=="__main__":
    main()
