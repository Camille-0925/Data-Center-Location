"""County screening with curated local-government evidence, not parcel approval."""
import json
from datetime import date
from pathlib import Path

FOLDER=Path(__file__).resolve().parent.parent/'data'
LABELS={'NO_OBVIOUS_RISK':'未察觉明显风险','RISK_DETECTED':'历史资料显示有风险','INSUFFICIENT_REFERENCE':'资料不足以判断'}

def apply_permitting(counties,as_of):
    records=json.loads((FOLDER/'permitting_references.json').read_text())
    index={r['county_fips']:r for r in records}
    for c in counties:
        if c['county_fips'] not in index:
            g=next(g for g in c['gates'] if g['gate_id']=='permitting_zoning')
            if g['risk_status']=='INSUFFICIENT_REFERENCE':
                g.update(risk_status='NO_OBVIOUS_RISK',display_label=LABELS['NO_OBVIOUS_RISK'],
                    reason='当前索引未发现明显许可或zoning风险；尚未找到可用的本地许可资料。',
                    risk_comparison=dict(method='user_selected_no_identified_risk_default',evidence_kind='no_local_reference',local_evidence_available=False,can_claim_project_approved=False,scope='Absence of an indexed risk flag; local approval pathway has not been established.'),
                    context_notes=g['context_notes']+['按用户指定的粗略初筛规则，资料不足时归类为未察觉明显风险；没有新增许可证据。'],
                    next_action='进入候选短名单后核实本地zoning及审批路径。')
            continue
        r=index[c['county_fips']];g=next(g for g in c['gates'] if g['gate_id']=='permitting_zoning')
        active_pause=r['kind']=='temporary_pause' and date.fromisoformat(as_of)<date.fromisoformat(r['assumed_pause_end'])
        risk=active_pause or r['kind']=='no_current_eligible_zoning'
        state='RISK_DETECTED' if risk else 'NO_OBVIOUS_RISK'
        g.update(risk_status=state,display_label=LABELS[state],reason=r['summary'],
            risk_comparison=dict(method='local_government_pathway_and_precedent',evidence_kind=r['kind'],checked_on=r['checked_on'],scope=r['scope'],can_claim_project_approved=False),
            used_reference_ids=sorted(set(g['used_reference_ids']+[r['record_id']])),
            context_notes=g['context_notes']+['以县市初筛为目的，有审批路径或历史先例即可保留候选；这不是所有地块的建设许可。','仅使用本县市官方资料，不将相邻县的zoning规则推广过来。','特殊许可流程本身不自动计为风险；明确暂停审议或尚无符合规定的分区土地则提示审批障碍。'],
            next_action='核实候选地块现行zoning、SUP/CUP/PUP要求以及资料中限制是否仍适用。')
        if r['kind']=='temporary_pause':
            g['risk_comparison'].update(assumed_pause_end=r['assumed_pause_end'],pause_end_is_calendar_approximation=True,active_pause=active_pause)
            g['context_notes'].append('按公告的8个月推算暂停期；CoVAC有by-right例外，是否适用暂停需向市核实。')
            if not active_pause:g['reason']='官方资料显示有CUP及部分by-right路径；历史暂停期按日历已结束，需核实是否延长。'
    return records
