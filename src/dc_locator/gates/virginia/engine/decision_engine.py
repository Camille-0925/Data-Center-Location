"""Trial only: historical delivery-point scale analogy, not spare MW estimation.
Run with Python standard library; baseline v2.5 is left unchanged.
"""
import copy, json, math
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
from .baseline_gate import evaluate as baseline_evaluate
from .permitting_expansion import apply_permitting
LABELS={'NO_OBVIOUS_RISK':'未察觉明显风险','RISK_DETECTED':'历史资料显示有风险','INSUFFICIENT_REFERENCE':'资料不足以判断'}

def distance(a,b):
    lat1,lat2=map(math.radians,[a['latitude'],b['latitude']])
    dl=math.radians(b['latitude']-a['latitude'])
    dn=math.radians(b['longitude']-a['longitude'])
    return 6371*2*math.asin(min(1,math.sqrt(math.sin(dl/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dn/2)**2)))

def donors(baseline):
    # Supplier is tied to each source project's delivery point, not every utility
    # listed in its county. Caroline projects serve REC; the others Dominion.
    suppliers={'51107':19876,'51087':19876,'51179':19876,'51033':40228}
    result=[]
    for c in baseline['county_results']:
        if c['county_fips'] not in suppliers: continue
        g=next(g for g in c['gates'] if g['gate_id']=='power_availability')
        result.append(dict(fips=c['county_fips'],name=c['county_name'],utility_id=suppliers[c['county_fips']],scale_mw=g['risk_comparison']['reference_scale_mw'],reference_ids=g['used_reference_ids']))
    return result

def candidates(fips,features,reference,max_distance_km):
    selected=[]
    for donor in reference:
        if donor['fips']==fips or donor['utility_id'] not in features[fips]['utility_ids']: continue
        km=distance(features[fips],features[donor['fips']])
        if km<=max_distance_km:
            selected.append(dict(donor,distance_km=km,weight=math.exp(-km/75)))
    return sorted(selected,key=lambda r:r['distance_km'])[:3]

def evaluate_internal(user_input,max_distance_km=250,as_of='2026-10-04'):
    baseline=baseline_evaluate(user_input,as_of=as_of)
    features=json.loads((HERE.parent/'data/county_features.json').read_text())
    reference=donors(baseline)
    output=copy.deepcopy(baseline['county_results'])
    filled=[]
    for c in output:
        g=next(g for g in c['gates'] if g['gate_id']=='power_availability')
        if g['risk_status']!='INSUFFICIENT_REFERENCE': continue
        chosen=candidates(c['county_fips'],features,reference,max_distance_km)
        if not chosen: continue
        scale=sum(r['weight']*r['scale_mw'] for r in chosen)/sum(r['weight'] for r in chosen)
        ratio=user_input['power_input_mw']/scale
        status='RISK_DETECTED' if ratio>1.25 else 'NO_OBVIOUS_RISK'
        g.update(risk_status=status,display_label=LABELS[status],reason=('需求超过同供电公司相近地区的规划规模参考及25%容差。' if status=='RISK_DETECTED' else '需求与同供电公司相近地区的规划规模参考未出现明显出入。'),
            risk_comparison=dict(required_facility_mw=user_input['power_input_mw'],reference_scale_mw=scale,demand_to_reference_ratio=ratio,risk_trigger_ratio=1.25,method='same_supplier_distance_weighted_planning_scale',maximum_analogue_distance_km=max_distance_km,estimated_available_spare_capacity_mw=None,analogue_counties=chosen),
            used_reference_ids=sorted(set(rid for d in chosen for rid in d['reference_ids'])),
            context_notes=['本县缺少规模证据，此项由其他地区规划规模类比得出。','EIA服务区域只说明供电公司在县内有配电设施，不保证候选地块由该公司供电。','规划需求不等于实际剩余容量，也不证明目标日前可交付；供电时间仍由单独Gate评估。',f'{max_distance_km:g} km距离上限、75 km权重衰减长度及25%容差是本次试算假设，未由实际可用容量校准。'],
            next_action='核实候选地块的实际供电公司、接入电压及容量安排。')
        states=[g['risk_status'] for g in c['gates']]
        c['overall_status']='RISK_DETECTED' if 'RISK_DETECTED' in states else ('INSUFFICIENT_REFERENCE' if 'INSUFFICIENT_REFERENCE' in states else 'NO_OBVIOUS_RISK')
        c['display_label']=LABELS[c['overall_status']]
        filled.append(c['county_fips'])
    permitting_records=apply_permitting(output,as_of)
    for c in output:
        states=[g['risk_status'] for g in c['gates']]
        c['overall_status']='RISK_DETECTED' if 'RISK_DETECTED' in states else ('INSUFFICIENT_REFERENCE' if 'INSUFFICIENT_REFERENCE' in states else 'NO_OBVIOUS_RISK')
        c['display_label']=LABELS[c['overall_status']]
    def counts(rows):
        return dict(Counter(next(g for g in c['gates'] if g['gate_id']=='power_availability')['risk_status'] for c in rows))
    all_gate_counts={gid:dict(Counter(next(g for g in c['gates'] if g['gate_id']==gid)['risk_status'] for c in output)) for gid in ('power_availability','time_to_power','permitting_zoning')}
    return dict(user_input=user_input,as_of=as_of,trial=True,baseline_power_counts=counts(baseline['county_results']),power_counts=counts(output),all_gate_counts=all_gate_counts,newly_supported_count=len(filled),newly_supported_fips=filled,county_results=output,permitting_reference_catalog=permitting_records)
