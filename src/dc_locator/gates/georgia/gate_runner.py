"""Georgia public API: two fields, full-state screening, concise output."""
import argparse,csv,json
from pathlib import Path
from .engine.decision_engine import evaluate_internal

def evaluate(user_input,as_of=None):
    internal=evaluate_internal(user_input,as_of)
    rows=[]
    for c in internal['county_results']:
        gates=[]
        for g in c['gates']:
            gid=g['gate_id'];status=g['risk_status']
            if status=='INSUFFICIENT_REFERENCE':reason='供电规模资料不足。' if gid=='power_availability' else '相关资料不足。'
            elif status=='NO_OBVIOUS_RISK':reason={'power_availability':'当前筛查未识别明显供电规模冲突。','time_to_power':'满容量供电目标日期未识别明显时间冲突。','permitting_zoning':'当前筛查未识别明显审批障碍。'}[gid]
            else:reason={'power_availability':'用电需求超过供电规模参考范围。','time_to_power':'满容量供电目标日期早于供电时间参考范围。','permitting_zoning':g['reason']}[gid]
            gates.append(dict(gate_id=gid,status=status,display_label=g['display_label'],reason=reason,next_action=g['next_action']))
        rows.append(dict(county_fips=c['county_fips'],county_name=c['county_name'],overall_status=c['overall_status'],display_label=c['display_label'],gates=gates))
    return dict(output_version='georgia_gates_v2.0',state='GA',evaluated_at=internal['evaluated_at'],user_input=dict(user_input),county_results=rows,summary=internal['summary'])

def export_csv(result,path):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['county_fips','county_name','overall_status','Power availability','Time-to-power','Permitting / zoning','Power原因','Time原因','Permitting原因'])
        for c in result['county_results']:w.writerow([c['county_fips'],c['county_name'],c['display_label']]+[g['display_label'] for g in c['gates']]+[g['reason'] for g in c['gates']])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--csv',type=Path);p.add_argument('--as-of');a=p.parse_args()
    try:
        result=evaluate(json.loads(a.input.read_text(encoding='utf-8')),a.as_of)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        if a.csv:export_csv(result,a.csv)
    except (ValueError,OSError) as exc:p.exit(2,str(exc)+'\n')
    print(json.dumps(result['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
