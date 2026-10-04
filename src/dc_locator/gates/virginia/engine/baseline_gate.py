"""Public entry point: required inputs only, automatic full-state screening."""
import argparse
from datetime import date
import json
import math
from pathlib import Path
from .real_data_adapter import EvidenceDatabase, evaluate_real

REQUIRED = {'power_input_mw', 'target_full_power_date'}
ALLOWED = REQUIRED
SEARCH_STATE = "VA"
PROJECT_TYPE = "new_build"


def evaluate(user_input, as_of=None, database=None):
    if not isinstance(user_input, dict): raise ValueError('用户输入必须是JSON对象')
    missing = REQUIRED - user_input.keys()
    if missing: raise ValueError('缺少必填项：' + ', '.join(sorted(missing)))
    extra = user_input.keys() - ALLOWED
    if extra: raise ValueError('用户输入仅接受必填字段，不接受：' + ', '.join(sorted(extra)))
    mw = user_input['power_input_mw']
    if isinstance(mw, bool) or not isinstance(mw, (int,float)) or not math.isfinite(mw) or mw <= 0:
        raise ValueError('power_input_mw须为大于0的有限数字，单位MW')
    target = user_input['target_full_power_date']
    if not isinstance(target, str): raise ValueError('目标日期须为YYYY-MM-DD')
    parsed = date.fromisoformat(target)
    if parsed.isoformat() != target: raise ValueError('目标日期须为YYYY-MM-DD')
    assessed = date.fromisoformat(as_of) if as_of else date.today()
    request = dict(user_input, request_id='REQUIRED_INPUT_REQUEST', request_version=1,
                   assessment_scope='land_use_diligence', search_state=SEARCH_STATE,
                   project_type=PROJECT_TYPE, power_input_basis='facility')
    payload = dict(request=request, gate_mode='historical_risk', enable_screening_estimates=True,
        estimation_config={'assumed_board_approval_date':assessed.isoformat()},
        risk_screening_config={'scale_deviation_tolerance':.25, 'timing_quantile':'p50',
            'infrastructure_scenario':'unspecified', 'approval_pathway_preference':'flexible'})
    # Deliberately omit candidate_county_fips, sites and project evidence.
    output = evaluate_real(payload, database, assessed.isoformat())
    output['input_contract_version'] = 'facility_input_virginia_v2.5'
    output['user_input'] = dict(user_input)
    output['resolved_system_defaults'] = dict(search_scope='all counties and independent cities in selected state',
        assessment_scope='land_use_diligence', search_state=SEARCH_STATE,
        project_type=PROJECT_TYPE, power_input_basis='facility',
        assumed_engineering_approval_date=assessed.isoformat(), date_is_assumption=True,
        approval_pathway_preference='flexible', infrastructure_scenario='unspecified',
        timing_quantile='p50', scale_deviation_tolerance=.25,
        site_scope='County-level placeholders; no user-selected construction parcel')
    output['county_results'] = [dict(county_fips=c['county_fips'], county_name=c['county_name'],
        overall_status=s['overall_status'], display_label=s['display_label'], can_exclude_county=False,
        gates=[{key:g[key] for key in ['gate_id','risk_status','display_label','reason','risk_comparison',
            'used_reference_ids','context_notes','next_action']} for g in s['gates']])
        for c in output['county_evidence_summary']
        for s in output['site_results'] if s['county_fips']==c['county_fips']]
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--as-of', help='系统评估日期，用于复现结果；不是用户表单字段')
    args=parser.parse_args()
    try:
        result=evaluate(json.loads(args.input.read_text(encoding='utf-8')),args.as_of)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    except (ValueError,OSError) as exc:
        parser.exit(2, '输入错误：'+str(exc)+'\n')

if __name__=='__main__': main()
