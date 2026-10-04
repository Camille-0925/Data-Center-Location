"""Georgia full-state historical/project-reference risk screening; standard library only."""
import argparse
from collections import Counter
from datetime import date,timedelta
import json,math,statistics
from pathlib import Path

LABELS={'NO_OBVIOUS_RISK':'未察觉明显风险','RISK_DETECTED':'历史资料显示有风险','INSUFFICIENT_REFERENCE':'资料不足以判断'}
DATA=Path(__file__).resolve().parent.parent/'data'
REQUIRED={'power_input_mw','target_full_power_date'}

def load_database(folder=DATA):
    folder=Path(folder)
    return {name:json.loads((folder/(name+'.json')).read_text(encoding='utf-8')) for name in ['county_directory','project_records','load_scale_references','timeline_references','permit_records','policy_records','sources_catalog','build_summary']}

def iso_date(value):
    if not isinstance(value,str):raise ValueError('日期须为YYYY-MM-DD')
    parsed=date.fromisoformat(value)
    if value!=parsed.isoformat():raise ValueError('日期须为YYYY-MM-DD')
    return parsed

def make_gate(gate_id,status,reason,comparison=None,ids=None,notes=None,next_action=''):
    return dict(gate_id=gate_id,status=status,risk_status=status,display_label=LABELS[status],reason=reason,
        risk_comparison=comparison or {},used_reference_ids=sorted(set(ids or [])),context_notes=notes or [],next_action=next_action,
        verified_status='UNKNOWN',can_exclude_county=False)

def evaluate(user_input,as_of=None,database=None):
    if not isinstance(user_input,dict):raise ValueError('用户输入必须是JSON对象')
    if set(user_input)!=REQUIRED:raise ValueError('仅接受必填字段：power_input_mw、target_full_power_date')
    mw=user_input['power_input_mw']
    if isinstance(mw,bool) or not isinstance(mw,(float,int)) or not math.isfinite(mw) or mw<=0:raise ValueError('用电需求须为大于0的有限数字，单位MW设施总负荷')
    target=iso_date(user_input['target_full_power_date']);assessed=iso_date(as_of) if as_of else date.today()
    db=database if database is not None else load_database()
    results=[];evidence_summary=[]
    all_t=db['timeline_references']
    if not all_t:raise ValueError('缺少Georgia工期参考数据')
    reference_catalog={}
    for key in ['project_records','load_scale_references','timeline_references','permit_records','policy_records']:
        for r in db[key]:reference_catalog[r['record_id']]=r
    for county in db['county_directory']:
        fips=county['county_fips'];projects=[r for r in db['project_records'] if r['county_fips']==fips and (not r.get('submitted_date') or iso_date(r['submitted_date'])<=assessed)]
        active=[r for r in projects if r['active_reference']]
        project_ids={r['record_id'] for r in active}
        loads=[r for r in db['load_scale_references'] if r['county_fips']==fips and r['project_record_id'] in project_ids]
        permits=[r for r in db['permit_records'] if r['county_fips']==fips and (not r.get('approval_date') or iso_date(r['approval_date'])<=assessed)]
        timelines=[r for r in all_t if fips in r['county_fips']]
        policies=[r for r in db['policy_records'] if r['county_fips']==fips]
        # Power: compare proposed peak connected loads, never spare supply or generation capacity.
        ids=[];notes=['参考规模是公开项目申报的峰值连接负荷，不能据此计算新项目可用剩余容量。']
        comparison=dict(required_facility_mw=mw,estimated_available_spare_capacity_mw=None,comparison_scope='county_project_precedent_only')
        if loads:
            ref=max(loads,key=lambda r:r['reference_scale_mw']);ratio=mw/ref['reference_scale_mw'];status='RISK_DETECTED' if ratio>1.25 else 'NO_OBVIOUS_RISK'
            comparison.update(reference_scale_mw=ref['reference_scale_mw'],reference_load_basis=ref['basis'],demand_to_reference_ratio=ratio,risk_trigger_ratio=1.25,method='same_county_largest_active_declared_peak_connected_load')
            reason='需求明显超出同县公开项目负荷参考规模。' if status=='RISK_DETECTED' else '需求与同县公开项目负荷参考规模未出现明显出入。'
            ids=[ref['record_id']]
        elif active or permits or timelines:
            status='NO_OBVIOUS_RISK';reason='同县存在数据中心或客户供电工程活动参考，未识别明显冲突；所需MW尚未定量比较。'
            ids=[r['record_id'] for r in active+permits+timelines]
            comparison.update(reference_scale_mw=None,method='qualitative_local_activity',mw_comparison_performed=False)
        else:
            status='INSUFFICIENT_REFERENCE';reason='未提取到同县可用于新建数据中心供电规模比较的资料。'
        comparison['local_applicant_reports'] = dict(infrastructure_insufficient_count=sum(r['applicant_infrastructure_response']=='no' for r in active),study_requested_count=sum(r['applicant_infrastructure_response']=='study_requested' for r in active))
        if comparison['local_applicant_reports']['infrastructure_insufficient_count']:
            notes.append('同县部分申报项目称现有输配电不足，或列出新建变电站/线路需求；这是对应项目的升级需求，不能直接认定整个县不可供电。')
        if mw>=100:notes.append('若由Georgia Power供电，100MW及以上新用户适用长期合同、最低账单及基础设施费用等商业条件；并非全州所有供电商统一规则。')
        power=make_gate('power_availability',status,reason,comparison,ids,notes,'确认候选地块供电商，并申请指定MW的负荷接入研究。')
        # Time: local projected schedules first, otherwise explicitly a Georgia utility analogue.
        refs=timelines or all_t
        low=statistics.median(r['duration_days_lower'] for r in refs);mid=statistics.median(r['duration_days_midpoint'] for r in refs);high=statistics.median(r['duration_days_upper'] for r in refs)
        early=assessed+timedelta(days=math.ceil(low));central=assessed+timedelta(days=math.ceil(mid));late=assessed+timedelta(days=math.ceil(high))
        window=early<=target<late
        timing_status='RISK_DETECTED' if target<early else 'NO_OBVIOUS_RISK'
        if target<early:reason='目标早于参考工期区间的最早日期，存在时间冲突。'
        elif window:reason='目标落在参考工期区间内，暂未识别明确时间冲突；部分季度假设会改变结论。'
        else:reason='目标不早于参考工期区间，暂未识别明显时间冲突。'
        time_gate=make_gate('time_to_power',timing_status,reason,dict(target_full_power_date=target.isoformat(),reference_completion_date=central.isoformat(),reference_completion_date_bounds=[early.isoformat(),late.isoformat()],reference_duration_days=dict(lower=low,midpoint=mid,upper=high),margin_days=(target-central).days,borderline=window,method='projected_survey_to_transmission_completion_analogue',reference_scope='same_county_project_analogue' if timelines else 'Georgia_Power_state_analogue',reference_sample_size=len(refs),assumed_new_project_survey_start=assessed.isoformat(),start_is_assumption=True,not_a_completed_delivery_dataset=True),[r['record_id'] for r in refs],['以评估日作为新项目进入类似勘测阶段的假设起点；没有按MW线性缩放工期。','参考的是大型新建输电工程的预计工期；工程完工不等于客户满容量通电。','州内类比可能跨供电商和工程类型，不表示每个county具备同样接入条件。'],'确认是否需要新建输电设施，向供电商取得该项目满容量供电计划。')
        # Permitting: preserve review-stage and jurisdiction; expired restrictions are not active risk flags.
        review=[r for r in active if r['regional_review_completed']]
        current=[r for r in policies if iso_date(r['effective_date'])<=assessed<=iso_date(r['possible_active_through'])]
        expired=[r for r in policies if assessed>iso_date(r['possible_active_through'])]
        pnotes=['DRI完成仅代表区域审查完成，不代表地方许可已批准；已有审批仅适用于原项目及对应辖区。']
        if current:
            pstatus='RISK_DETECTED';preason='县内部分辖区存在生效中的新建数据中心暂停受理规定，需核实选址是否落在其范围。';pids=[r['record_id'] for r in current]
        elif permits:
            pstatus='NO_OBVIOUS_RISK';preason='县内有官方确认的审批先例，已收集资料未显示适用中的明确禁止。';pids=[r['record_id'] for r in permits]
        elif review:
            pstatus='NO_OBVIOUS_RISK';preason='县内有已完成区域审查的项目，提供规划审批路径参考；具体地方许可尚未确认。';pids=[r['record_id'] for r in review]
        else:
            pstatus='INSUFFICIENT_REFERENCE';preason='未提取到同县足以判断新项目审批路径的地方资料。';pids=[r['record_id'] for r in projects]
        if expired:pnotes.append('已记录但过期的暂停规定不触发当前风险；尚未完成所有后续法规的检索。')
        permit_gate=make_gate('permitting_zoning',pstatus,preason,dict(active_restrictions=current,expired_restrictions=expired,approval_precedent_count=len(permits),completed_regional_review_count=len(review),countywide_permission_confirmed=False),pids,pnotes,'核实具体地块所在城市或非建制地区、现行分区及特别许可要求。')
        gates=[power,time_gate,permit_gate];states={g['risk_status'] for g in gates}
        overall='RISK_DETECTED' if 'RISK_DETECTED' in states else ('INSUFFICIENT_REFERENCE' if 'INSUFFICIENT_REFERENCE' in states else 'NO_OBVIOUS_RISK')
        results.append(dict(county_fips=fips,county_name=county['county_name'],overall_status=overall,display_label=LABELS[overall],can_exclude_county=False,gates=gates))
        evidence_summary.append(dict(county_fips=fips,county_name=county['county_name'],dri_project_count=len(projects),active_project_count=len(active),load_reference_count=len(loads),local_timeline_count=len(timelines),approval_record_count=len(permits),policy_record_count=len(policies)))
    used={rid for c in results for g in c['gates'] for rid in g['used_reference_ids']}
    sources={sid for rid in used for sid in reference_catalog[rid].get('source_ids',[])}
    sources.add('gp_pledge')
    return dict(input_contract_version='facility_input_georgia_v1.0',gate_mode='historical_risk',risk_rule_version='georgia_reference_risk_v1',evaluated_at=assessed.isoformat(),user_input=dict(user_input),resolved_system_defaults=dict(search_state='GA',project_type='new_build',power_input_basis='facility',search_scope='all_159_Georgia_counties',scale_deviation_tolerance=.25,assumed_engineering_start=assessed.isoformat(),date_is_assumption=True,site_scope='county_placeholders_no_selected_parcel'),county_results=results,county_evidence_summary=evidence_summary,summary=dict(counties=len(results),overall_status_counts=dict(Counter(c['overall_status'] for c in results)),gate_status_counts={gid:dict(Counter(next(g['risk_status'] for g in c['gates'] if g['gate_id']==gid) for c in results)) for gid in ['power_availability','time_to_power','permitting_zoning']}),reference_catalog={rid:reference_catalog[rid] for rid in sorted(used)},source_catalog={sid:db['sources_catalog'][sid] for sid in sorted(sources)},data_build_summary=db['build_summary'],risk_interpretation='No obvious mismatch with available references is not confirmed feasibility. County risk flags do not automatically exclude the county; retain jurisdiction and scenario scope.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--as-of',help='System assessment date for reproducibility; not a user field');a=p.parse_args()
    try:a.output.write_text(json.dumps(evaluate(json.loads(a.input.read_text(encoding='utf-8')),a.as_of),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    except (OSError,ValueError) as exc:p.exit(2,str(exc)+'\n')
if __name__=='__main__':main()
