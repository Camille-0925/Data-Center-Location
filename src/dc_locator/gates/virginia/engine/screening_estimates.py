"""Transparent preliminary screening using public analogues.
This adds screening judgments without overwriting the three confirmed gates.
No regression model, calibrated probabilities, or spare-capacity estimate is implied.
"""
from datetime import date, datetime, timedelta
import re
from .feasibility_gates import _profile

MODEL_VERSION='public_analogue_screening_v1'


def _date(value):
    if not isinstance(value,str):return None
    for fmt in ('%m/%d/%Y','%Y-%m-%d'):
        try:return datetime.strptime(value,fmt).date()
        except ValueError:pass
    return None


def _quantile(numbers,p):
    values=sorted(numbers)
    position=(len(values)-1)*p
    low=int(position);high=min(low+1,len(values)-1)
    return values[low]+(values[high]-values[low])*(position-low)


def engineering_duration_reference(db, as_of, owner=None):
    """Completed customer-service upgrade groups, approval to actual in-service.
    Group suffixes by base Upgrade Id, retaining latest component completion.
    This is a historical, completion-conditioned engineering reference.
    """
    groups={}
    incomplete_groups=set()
    for record in db.engineering.values():
        a=record['attributes']
        if owner and str(a.get('Transmission Owner','')).casefold()!=owner.casefold():continue
        key=(a.get('Transmission Owner'),str(a.get('Upgrade Id')).split('.')[0])
        if a.get('Status')!='IS':
            incomplete_groups.add(key)
            continue
        if 'customer service' not in str(a.get('Driver','')).lower():continue
        start=_date(a.get('PJM Board Approval Date'));end=_date(a.get('Actual In Service Date'))
        if not start or not end or not start<=end<=as_of:
            incomplete_groups.add(key)
            continue
        # Same owner/base upgrade = one reference group, not each component as a new sample.
        group=groups.setdefault(key,{'starts':[],'ends':[],'ids':[]})
        group['starts'].append(start);group['ends'].append(end);group['ids'].append(record['record_id'])
    samples=[dict(duration_days=(max(g['ends'])-min(g['starts'])).days,source_record_ids=g['ids'])
             for key,g in groups.items() if key not in incomplete_groups]
    if len(samples)<5:
        return dict(status='INSUFFICIENT_REFERENCE',sample_count=len(samples),owner_filter=owner)
    durations=[r['duration_days'] for r in samples]
    return dict(status='AVAILABLE_REFERENCE',sample_count=len(samples),owner_filter=owner,
        geographic_scope='Virginia completed customer-service transmission engineering',
        start_definition='PJM Board Approval Date',end_definition='Actual In Service Date',
        quantile_method='linear interpolation on grouped durations',
        p25_days=round(_quantile(durations,.25)),p50_days=round(_quantile(durations,.5)),
        p75_days=round(_quantile(durations,.75)),source_record_ids=[i for r in samples for i in r['source_record_ids']],
        limitations=['Completed projects only: unfinished/cancelled/delayed projects create selection bias.',
            'Not data-center full-capacity delivery; no MW scaling or locality-specific calibration.',
            'Pre-approval, land, procurement and additional customer works are not included.'])


def _screen(gate, verdict, label, method, reason, observed=None, assumptions=None, records=None, next_action=''):
    return dict(gate_id=gate,screening_verdict=verdict,display_label=label,method=method,
        evidence_type='proxy_analogue',confidence='low_uncalibrated',reason=reason,
        observed=observed or {},assumptions=assumptions or [],source_record_ids=records or [],
        next_action=next_action,can_support_final_gate_pass=False,can_exclude_county=False)


def add_screening_estimates(output, payload, db):
    """Mutate output with explicit screening decisions and numeric reference ranges."""
    as_of=date.fromisoformat(output['evaluated_at'])
    config=payload.get('estimation_config',{})
    if not isinstance(config,dict):raise ValueError('estimation_config must be an object')
    owner=config.get('transmission_owner_filter')
    if owner is not None and (not isinstance(owner,str) or not owner):raise ValueError('invalid transmission_owner_filter')
    start_text=config.get('assumed_board_approval_date',as_of.isoformat())
    start=_date(start_text)
    if start is None:raise ValueError('assumed_board_approval_date must be a date')
    reference=engineering_duration_reference(db,as_of,owner)
    required,_,missing_power,missing_time=_profile(payload['request'])
    target=_date(payload['request'].get('target_full_power_date'))
    counties={r['county_fips']:r for r in output['county_evidence_summary']}
    output['screening_model_version']=MODEL_VERSION
    output['engineering_duration_reference']=reference
    for result in output['site_results']:
        fips=result['county_fips'];county=counties[fips]
        projects=[p for p in db.projects if p['county_fips']==fips]
        if missing_power:
            capacity=_screen('power_availability','INPUT_REQUIRED','需补项目需求','none','容量需求未明确。')
        elif projects:
            # Report analogues, not headroom. Do not sum unrelated customer loads.
            peak=max(max(p['projected_2029_summer_load_mw'],p['projected_2029_winter_load_mw']) for p in projects)
            fits=required<=peak
            capacity=_screen('power_availability','ESTIMATED_FAVORABLE' if fits else 'SCALE_CONCERN',
                '有同规模规划先例' if fits else '需求超出现有先例规模','historical_planned_load_scale',
                '比较需求与同县公开规划负荷的规模；不推断新客户剩余可用MW。',
                observed=dict(required_facility_mw=required,largest_reference_peak_load_mw=peak,
                    demand_to_reference_scale_ratio=required/peak,estimated_available_spare_capacity_mw=None),
                assumptions=['Historic planning precedent is useful for preliminary infrastructure screening; it does not reserve capacity.'],
                records=[p['project_ref'] for p in projects],next_action='核实新用户的实际容量预留及接入方案。')
        elif county['public_record_counts']['data_center_related_permits']:
            capacity=_screen('power_availability','PRECEDENT_ONLY','有数据中心活动先例，容量待核实',
                'permitted_activity_context','相关许可表明当地有数据中心活动；不据此计算供电容量。',
                observed=dict(related_permit_record_count=county['public_record_counts']['data_center_related_permits'],
                    estimated_available_spare_capacity_mw=None),
                next_action='取得utility容量评估，不能用许可数量换算MW。')
        else:
            capacity=_screen('power_availability','REQUIRES_DILIGENCE','优先补供电资料','no_capacity_analogue',
                '目前资料没有可用的本地容量先例；保留候选而不自动通过或淘汰。',
                next_action='先核实供电接入条件。')
        if missing_power or missing_time:
            timing=_screen('time_to_power','INPUT_REQUIRED','需补项目需求','none','所需容量或目标日期未明确。')
        elif reference['status']!='AVAILABLE_REFERENCE':
            timing=_screen('time_to_power','REQUIRES_DILIGENCE','工期参考不足','completed_engineering_duration',
                '不足五个可比工程组，不产生数值推算。')
        else:
            dates={name:(start+timedelta(days=reference[name+'_days'])).isoformat() for name in ('p25','p50','p75')}
            if target<date.fromisoformat(dates['p25']):verdict,label='SCHEDULE_RISK','假设情景下工期紧张'
            elif target>=date.fromisoformat(dates['p75']):verdict,label='ESTIMATED_FAVORABLE','假设情景下工程窗口较宽'
            else:verdict,label='BORDERLINE_SCHEDULE','假设情景下工期处于参考区间'
            timing=_screen('time_to_power',verdict,label,'completed_customer_service_engineering_analogue',
                '以历史审批到工程投运的工期作初筛；不是客户满容量交付预测。',
                observed=dict(assumed_board_approval_date=start.isoformat(),target_full_power_date=target.isoformat(),
                    engineering_completion_scenario_dates=dates,reference_sample_count=reference['sample_count'],
                    estimated_customer_full_power_date=None),
                assumptions=['Treat the assumed date as if required engineering were board-approved then; actual approval is not established.',
                    'Past completed customer-service transmission engineering is a rough analogue, without local/MW calibration.'],
                records=reference['source_record_ids'],next_action='核实工程是否已批准、真实前置条件和用户容量交付安排。')
        observations=result['public_site_observations']
        exact_permits=observations['permit_records']
        usable=[]
        for p in exact_permits:
            if 'zoning' not in str(p.get('permit_type','')).lower():continue
            issued=p.get('issued_or_approved_at');expiry=p.get('expires_at')
            if issued and date.fromisoformat(issued[:10])<=as_of and (not expiry or date.fromisoformat(expiry[:10])>=as_of):usable.append(p)
        county_permits=[p for p in db.permits_for(fips) if p['status'] in {'Issued','ACTIVE'}
            and p.get('issued_or_approved_at') and date.fromisoformat(p['issued_or_approved_at'][:10])<=as_of
            and (not p.get('expires_at') or date.fromisoformat(p['expires_at'][:10])>=as_of)]
        if usable:
            permitting=_screen('permitting_zoning','ESTIMATED_FAVORABLE','同地块有zoning许可先例',
                'same_parcel_zoning_permit_precedent','同PIN有已发zoning许可，是用地尽调的积极线索。',
                observed=dict(zoning_records_not_recorded_as_expired_count=len(usable)),
                assumptions=['Prior permits may concern other tenants/phases or uses; current-project applicability is not established.',
                    'An empty expiry field means no expiry shown, not proof of perpetual validity.'],
                records=[p['record_id'] for p in usable],next_action='核实当前项目是否可沿用批准及全部特殊条件。')
        elif county_permits:
            permitting=_screen('permitting_zoning','PRECEDENT_ONLY','同县有数据中心许可先例',
                'county_permit_precedent','同县公开许可是初筛线索，不是当前地块的批准。',
                observed=dict(issued_or_active_related_record_count=len(county_permits)),
                assumptions=['Permit descriptions identify data-center-related works, not necessarily a new-build land-use approval.'],
                records=[p['record_id'] for p in county_permits[:10]],next_action='选择地块并核实具体允许用途。')
        else:
            permitting=_screen('permitting_zoning','REQUIRES_DILIGENCE','优先补用地资料','no_permit_analogue',
                '当前索引没有可用的本地许可先例，不能由缺少记录推断禁止。',next_action='查候选地块的现行用途及审批路径。')
        estimates=[capacity,timing,permitting]
        for gate,estimate in zip(result['gates'],estimates):
            if gate['status'] in {'PASS','FAIL'}:
                estimate.update(screening_verdict='CONFIRMED_'+gate['status'],display_label='证据确认'+gate['status'],
                    evidence_type='project_confirmation',can_support_final_gate_pass=gate['status']=='PASS',
                    confidence='verified_within_declared_scope',source_record_ids=gate['used_evidence_ids'],
                    reason=gate['reason'],confirmed_gate_result=gate)
            elif gate['input_status']=='INPUT_REQUIRED':
                estimate.update(screening_verdict='INPUT_REQUIRED',display_label='需补项目需求')
        result['screening_estimates']=estimates
        verdicts=[e['screening_verdict'] for e in estimates]
        local_support=any(e['screening_verdict'] in {'ESTIMATED_FAVORABLE','PRECEDENT_ONLY','CONFIRMED_PASS'}
                          for e in (capacity,permitting))
        result['screening_overall_status']=('INPUT_REQUIRED' if 'INPUT_REQUIRED' in verdicts else
            'CONFIRMED_INFEASIBLE' if 'CONFIRMED_FAIL' in verdicts else
            'FOLLOW_UP_RISK' if any(v in {'SCHEDULE_RISK','SCALE_CONCERN'} for v in verdicts) else
            'PRIORITIZE_DILIGENCE' if local_support
            else 'COLLECT_LOCAL_EVIDENCE')
    output['screening_limitations']=['Screening labels are preliminary action guidance, not confirmed physical feasibility.',
        'Empirical quartiles are reference-distribution statistics, not calibrated confidence intervals or success probabilities.',
        'Do not turn low/absent proxy support into county exclusion.']
    return output
