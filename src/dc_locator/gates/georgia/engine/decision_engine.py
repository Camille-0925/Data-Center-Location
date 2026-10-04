"""Georgia screening: preserve local evidence, supplement power, apply permitting default."""
import copy,json,math
from collections import Counter
from pathlib import Path
from .baseline_gate import evaluate as baseline_evaluate,load_database

DATA=Path(__file__).resolve().parent.parent/'data'
LABELS={'NO_OBVIOUS_RISK':'未察觉明显风险','RISK_DETECTED':'历史资料显示有风险','INSUFFICIENT_REFERENCE':'资料不足以判断'}

def supplier_id(name):
    name=name.lower().strip()
    if name in {'georgia power','georgia power company','ga power'}:return 7140
    if 'cartersville electric' in name:return 3108
    if 'central georgia electric' in name:return 3248
    if name=='jefferson energy':return 9689
    # MEAG is a wholesale agency; do not treat its members as one retail utility.
    return None

def distance(a,b):
    lat1,lat2=map(math.radians,[a['latitude'],b['latitude']])
    dl=math.radians(b['latitude']-a['latitude']);dn=math.radians(b['longitude']-a['longitude'])
    return 6371*2*math.asin(min(1,math.sqrt(math.sin(dl/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dn/2)**2)))

def evaluate_internal(user_input,as_of=None,database=None):
    baseline=baseline_evaluate(user_input,as_of,database)
    db=database if database is not None else load_database()
    result=copy.deepcopy(baseline)
    features=json.loads((DATA/'county_features.json').read_text())
    projects={r['record_id']:r for r in db['project_records']}
    donors=[]
    for c in baseline['county_results']:
        gate=c['gates'][0]
        for rid in gate['used_reference_ids']:
            r=result['reference_catalog'].get(rid,{})
            if 'reference_scale_mw' not in r:continue
            project_id=r.get('project_record_id')
            p=projects[project_id];utility=supplier_id(p['energy_provider'])
            if utility is None or utility not in features[c['county_fips']]['utility_ids']:continue
            donors.append(dict(fips=c['county_fips'],name=c['county_name'],utility_id=utility,scale_mw=r['reference_scale_mw'],reference_id=rid))
    supplemented=[];permit_defaults=[]
    for c in result['county_results']:
        power=c['gates'][0]
        if power['risk_status']=='INSUFFICIENT_REFERENCE':
            chosen=[]
            for d in donors:
                if d['fips']==c['county_fips'] or d['utility_id'] not in features[c['county_fips']]['utility_ids']:continue
                km=distance(features[c['county_fips']],features[d['fips']])
                if km<=250:chosen.append(dict(d,distance_km=km,weight=math.exp(-km/75)))
            chosen=sorted(chosen,key=lambda r:r['distance_km'])[:3]
            if chosen:
                ref=sum(d['weight']*d['scale_mw'] for d in chosen)/sum(d['weight'] for d in chosen)
                ratio=user_input['power_input_mw']/ref
                status='RISK_DETECTED' if ratio>1.25 else 'NO_OBVIOUS_RISK'
                power.update(status=status,risk_status=status,display_label=LABELS[status],reason='用电需求超过供电规模参考范围。' if status=='RISK_DETECTED' else '当前筛查未识别明显供电规模冲突。')
                power['risk_comparison'].update(reference_scale_mw=ref,demand_to_reference_ratio=ratio,risk_trigger_ratio=1.25,method='same_supplier_distance_weighted_planning_scale',analogue_counties=chosen,maximum_analogue_distance_km=250,estimated_available_spare_capacity_mw=None)
                power['used_reference_ids']=sorted({d['reference_id'] for d in chosen})
                supplemented.append(c['county_fips'])
        permit=c['gates'][2]
        if permit['risk_status']=='INSUFFICIENT_REFERENCE':
            permit.update(status='NO_OBVIOUS_RISK',risk_status='NO_OBVIOUS_RISK',display_label=LABELS['NO_OBVIOUS_RISK'],reason='当前筛查未识别明显审批障碍。')
            permit['risk_comparison'].update(method='user_selected_no_identified_risk_default',local_evidence_available=False,countywide_permission_confirmed=False)
            permit_defaults.append(c['county_fips'])
        states={g['risk_status'] for g in c['gates']}
        status='RISK_DETECTED' if 'RISK_DETECTED' in states else ('INSUFFICIENT_REFERENCE' if 'INSUFFICIENT_REFERENCE' in states else 'NO_OBVIOUS_RISK')
        c.update(overall_status=status,display_label=LABELS[status])
    # Include each borrowed reference's source metadata for internal traceability.
    for d in donors:
        record=next(r for r in db['load_scale_references'] if r['record_id']==d['reference_id'])
        result['reference_catalog'][d['reference_id']]=record
        for sid in record['source_ids']:result['source_catalog'][sid]=db['sources_catalog'][sid]
    result['summary']=dict(counties=len(result['county_results']),overall_status_counts=dict(Counter(c['overall_status'] for c in result['county_results'])),gate_status_counts={gid:dict(Counter(next(g['risk_status'] for g in c['gates'] if g['gate_id']==gid) for c in result['county_results'])) for gid in ('power_availability','time_to_power','permitting_zoning')})
    result['internal_changes']=dict(power_supplemented_fips=supplemented,permitting_default_fips=permit_defaults,donors=donors)
    return result
