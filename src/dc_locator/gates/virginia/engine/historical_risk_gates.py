"""Historical-reference risk screening, independent of construction approval."""
from calendar import monthrange
from copy import deepcopy
from datetime import date
import math

LABELS = {'NO_OBVIOUS_RISK': '未察觉明显风险', 'RISK_DETECTED': '历史资料显示有风险',
          'INSUFFICIENT_REFERENCE': '资料不足以判断', 'INPUT_REQUIRED': '需补充用户输入'}


def add_months(start, months):
    m = start.year * 12 + start.month - 1 + months
    y, month = divmod(m, 12)
    return date(y, month + 1, min(start.day, monthrange(y, month + 1)[1]))


def apply_historical_risk_gates(output, payload, db):
    config = payload.get('risk_screening_config', {})
    if not isinstance(config, dict): raise ValueError('risk_screening_config must be an object')
    tolerance = config.get('scale_deviation_tolerance', 0.25)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or not 0 <= tolerance <= 1:
        raise ValueError('scale_deviation_tolerance must be between 0 and 1')
    scenario = config.get('infrastructure_scenario', 'unspecified')
    if scenario not in {'unspecified', 'new_major_infrastructure'}:
        raise ValueError('infrastructure_scenario must be unspecified or new_major_infrastructure')
    pathway = config.get('approval_pathway_preference', 'flexible')
    if pathway not in {'flexible', 'by_right_only'}: raise ValueError('invalid approval_pathway_preference')
    quantile = config.get('timing_quantile', 'p50')
    if quantile not in {'p25', 'p50', 'p75'}: raise ValueError('invalid timing_quantile')
    final_order = config.get('assumed_final_order_date')
    if final_order is not None:
        if not isinstance(final_order, str): raise ValueError('assumed_final_order_date must be ISO date')
        date.fromisoformat(final_order)
    output['gate_mode'] = 'historical_risk'
    output['risk_rule_version'] = 'historical_risk_v1'
    output['historical_risk_reference_catalog'] = [dict(
        {k:v for k,v in r.items() if k != 'excerpt'},
        source_url=db.sources.get(r['source_id'], {}).get('url')) for r in db.risk_references]
    output['policy_risk_reference_catalog'] = deepcopy(db.policy_references)
    output['risk_screening_config'] = dict(scale_deviation_tolerance=tolerance,
        infrastructure_scenario=scenario, approval_pathway_preference=pathway, timing_quantile=quantile,
        assumed_final_order_date=final_order)
    output['risk_interpretation'] = 'No obvious mismatch with available references is not confirmed feasibility. Risk flags do not automatically exclude a county.'
    as_of = date.fromisoformat(output['evaluated_at'])
    mapped = {}
    for result in output['site_results']:
        result['verified_overall_status'] = result['overall_status']
        fips = result['county_fips']
        refs = [r for r in db.risk_references if r['county_fips'] == fips]
        policies = [p for p in db.policy_references if p['county_fips'] == fips and
                    (not p.get('effective_date') or date.fromisoformat(p['effective_date']) <= as_of)]
        estimates = {e['gate_id']: e for e in result['screening_estimates']}
        for gate in result['gates']:
            original = gate['status']
            gate['verified_status'] = original
            gate['verified_reason'] = gate['reason']
            est = estimates[gate['gate_id']]
            state = 'INSUFFICIENT_REFERENCE'
            reason = est['reason']
            comparison = {}
            ids = list(est['source_record_ids'])
            notes = []
            observations = deepcopy(est['observed'])
            if gate['input_status'] == 'INPUT_REQUIRED':
                state, reason = 'INPUT_REQUIRED', '请补充容量、日期等必要需求，再比较历史资料。'
            elif original in {'PASS', 'FAIL'}:
                state = 'NO_OBVIOUS_RISK' if original == 'PASS' else 'RISK_DETECTED'
                reason = gate['verified_reason']
            elif gate['reason_code'] == 'CONFLICTING_EVIDENCE':
                reason = '证据冲突，尚不能形成一致的风险判断。'
            elif gate['gate_id'] == 'power_availability':
                required = gate['requirement_summary']['required_facility_mw']
                load_ref = next((r for r in refs if r['kind'] == 'infrastructure_load_scale'), None)
                scale = observations.get('largest_reference_peak_load_mw')
                if load_ref:
                    scale = load_ref['values']['reference_scale_mw']
                    ids.append(load_ref['record_id'])
                    observations['reference_load_basis'] = load_ref['values']['basis']
                    notes.append(load_ref['note'])
                if scale:
                    ratio = required / scale
                    state = 'RISK_DETECTED' if ratio > 1 + tolerance else 'NO_OBVIOUS_RISK'
                    comparison = dict(required_facility_mw=required, reference_scale_mw=scale,
                        demand_to_reference_ratio=ratio, risk_trigger_ratio=1+tolerance,
                        ratio_rule_basis='Declared heuristic tolerance, not calibrated physical capacity.')
                    reason = '需求明显超出公开规划负荷参考规模。' if state == 'RISK_DETECTED' else '需求与公开规划负荷参考规模未出现明显出入。'
                    notes.append('比较的是规划规模，不是可用容量估计；远期规划不能证明目标日前可交付。')
                elif any(r['kind'] == 'data_center_activity_precedent' for r in refs):
                    activity = [r for r in refs if r['kind'] == 'data_center_activity_precedent']
                    state, reason = 'NO_OBVIOUS_RISK', '同县有官方或运营商公开的数据中心/供电规划活动参考，未从这些资料识别明显冲突；规模尚未定量比较。'
                    comparison = dict(required_facility_mw=required,reference_scale_mw=None,
                        mw_comparison_performed=False,method='indexed_local_activity_precedent')
                    ids.extend(r['record_id'] for r in activity)
                    notes.extend(r['note'] for r in activity)
                    observations['local_activity_reference_count'] = len(activity)
                elif est['screening_verdict'] == 'PRECEDENT_ONLY':
                    state, reason = 'NO_OBVIOUS_RISK', '同县有数据中心活动先例，未从该活动资料发现明显冲突；规模尚未定量比较。'
                    notes.append('仅有活动先例；不表示所需MW已被评估。')
                for ref in refs:
                    if ref['kind'] == 'qualified_site_context':
                        ids.append(ref['record_id'])
                        notes.append(ref['note'])
                observations['estimated_available_spare_capacity_mw'] = None
                for ref in refs:
                    if ref['kind'] == 'contextual_capacity_constraint':
                        notes.append('Leesburg历史案例出现过无过渡供电及扩建依赖；子区域情形未自动外推到整个县。')
                        ids.append(ref['record_id'])
            elif gate['gate_id'] == 'time_to_power':
                dates = observations.get('engineering_completion_scenario_dates', {})
                local = next((r for r in refs if r['kind'] == 'major_infrastructure_duration'), None)
                start = observations.get('assumed_board_approval_date')
                reference_date = date.fromisoformat(dates[quantile]) if quantile in dates else None
                if local and scenario == 'new_major_infrastructure' and start:
                    reference_date = add_months(date.fromisoformat(final_order or start), local['values']['duration_months'])
                    comparison.update(reference_duration_months=local['values']['duration_months'],
                        start_basis='Assumed final SCC order date; separate field if supplied, otherwise shared assumed approval date.',
                        assumed_final_order_date=final_order or start,
                        method='same_county_single_project_projected_major_infrastructure_duration')
                    ids.append(local['record_id'])
                    notes.append(local['note'])
                elif local and start:
                    observations['major_infrastructure_alternative_date'] = add_months(date.fromisoformat(start),local['values']['duration_months']).isoformat()
                    notes.append('若实际需要同类大型新建基础设施，47个月情景可能更适用；当前未确定此需求。')
                if reference_date:
                    checks = [dict(target_date=r['date'], facility_mw=r['facility_mw'],
                        margin_days=(date.fromisoformat(r['date'])-reference_date).days)
                        for r in gate.get('requirement_summary', [])]
                    if checks:
                        state = 'RISK_DETECTED' if any(c['margin_days'] < 0 for c in checks) else 'NO_OBVIOUS_RISK'
                        comparison.update(reference_completion_date=reference_date.isoformat(),milestone_comparisons=checks,timing_quantile=quantile)
                        reason = '目标日期早于所选参考工期情景，存在时间冲突。' if state == 'RISK_DETECTED' else '各阶段目标日期与所选参考工期情景未出现明显冲突。'
            elif gate['gate_id'] == 'permitting_zoning':
                if est['screening_verdict'] in {'ESTIMATED_FAVORABLE', 'PRECEDENT_ONLY'}:
                    state, reason = 'NO_OBVIOUS_RISK', '已有许可活动提供初筛先例，当前资料未识别明确禁止。'
                if policies:
                    ids.extend(p['record_id'] for p in policies)
                    observations['policy_context'] = policies
                    notes.append('存在新增特殊许可或资格核查路径；旧许可不能直接替代新项目审批。')
                    if pathway == 'by_right_only':
                        state, reason = 'RISK_DETECTED', '用户只接受直接允许建设；现有政策资料提示特殊许可或资格核查，与该偏好存在潜在冲突。'
                        comparison = {'approval_pathway_preference':pathway,'scope':'Potential pathway risk; actual parcel eligibility remains unresolved.'}
            gate.update(status=state, risk_status=state, display_label=LABELS[state],reason=reason,
                decision_basis='project_evidence' if original in {'PASS','FAIL'} else 'historical_reference',
                is_approximation=original not in {'PASS','FAIL'},
                risk_comparison=comparison,reference_observed=observations,
                used_reference_ids=sorted(set(ids)), assumptions=est['assumptions'],context_notes=notes,
                coverage_scope='Current indexed records; no countywide physical or legal feasibility claim.',
                can_exclude_county=False,next_action=est['next_action'])
        states = [g['risk_status'] for g in result['gates']]
        overall = 'INPUT_REQUIRED' if 'INPUT_REQUIRED' in states else 'RISK_DETECTED' if 'RISK_DETECTED' in states else 'INSUFFICIENT_REFERENCE' if 'INSUFFICIENT_REFERENCE' in states else 'NO_OBVIOUS_RISK'
        result.update(overall_status=overall,display_label=LABELS[overall],can_claim_verified_feasible=False,
            can_exclude_county=False,risk_count=states.count('RISK_DETECTED'),
            insufficient_reference_count=states.count('INSUFFICIENT_REFERENCE'))
        mapped[(result['site_id'],result['power_plan_id'])] = result
    for county in output['county_evidence_summary']:
        for entry in county['site_plan_results']:
            result = mapped[(entry['site_id'],entry['power_plan_id'])]
            entry['verified_status'] = entry['status']
            entry.update(status=result['overall_status'],display_label=result['display_label'],can_exclude_county=False)
    return output
