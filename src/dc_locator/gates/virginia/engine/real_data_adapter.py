"""Connect prepared real Virginia public records to the three existing gates.
Runtime: Python standard library only. Public observations never become customer
capacity commitments or complete permitting approvals by automatic conversion.
"""
from pathlib import Path
from collections import Counter
from copy import deepcopy
from datetime import date
import argparse
import json
import gzip
import math

from .feasibility_gates import evaluate_bundle


class EvidenceDatabase:
    def __init__(self, folder=None):
        self.folder=Path(folder) if folder else Path(__file__).resolve().parent.parent/'data'
        def read(name):
            path=self.folder/(name+'.json')
            if path.exists():return json.loads(path.read_text(encoding='utf-8'))
            with gzip.open(self.folder/(name+'.json.gz'),'rt',encoding='utf-8') as file:return json.load(file)
        self.counties={r['county_fips']:r for r in read('county_directory')}
        self.sources={r['source_id']:r for r in read('sources')}
        self.permits=read('permit_records')
        self.parcels=read('linked_parcels')
        self.zones=read('zoning_features')
        self.projects=read('public_load_projects')
        self.engineering={r['record_id']:r for r in read('pjm_virginia_engineering')}
        self.version=read('build_summary')['data_version']
        self.risk_references=read('historical_risk_references') if (self.folder/'historical_risk_references.json').exists() else []
        self.policy_references=read('policy_risk_references') if (self.folder/'policy_risk_references.json').exists() else []

    def permits_for(self, fips, pins=None):
        return [r for r in self.permits if r['county_fips']==fips
                and (pins is None or r['parcel_pin'] in pins)]


def point_in_esri(x,y,geometry):
    """Even-odd containment for an ESRI polygon; boundaries are included.
    Only a point observation, not an area intersection or legal assessment.
    """
    inside=False
    for ring in (geometry or {}).get('rings',[]):
        if len(ring)<3:continue
        for a,b in zip(ring,ring[1:]+ring[:1]):
            ax,ay=a[:2];bx,by=b[:2]
            cross=(x-ax)*(by-ay)-(y-ay)*(bx-ax)
            if abs(cross)<1e-12 and min(ax,bx)-1e-12<=x<=max(ax,bx)+1e-12 and min(ay,by)-1e-12<=y<=max(ay,by)+1e-12:
                return True
            if (ay>y)!=(by>y) and x < ax+(y-ay)*(bx-ax)/(by-ay):
                inside=not inside
    return inside


def _source_fields(db, record):
    s=db.sources[record['source_id']]
    return dict(source_id=record['source_id'],source_url=s.get('url'),local_file=s.get('local_file'),
                source_locator=record['source_locator'])


def _site_point(site, parcels):
    if site.get('longitude') is not None or site.get('latitude') is not None:
        x,y=site.get('longitude'),site.get('latitude')
        if (isinstance(x,bool) or isinstance(y,bool) or not isinstance(x,(int,float)) or not isinstance(y,(int,float))
                or not math.isfinite(x) or not math.isfinite(y) or not -180<=x<=180 or not -90<=y<=90):
            raise ValueError('site latitude/longitude must be finite geographic coordinates')
        return x,y,'user_supplied_site_point'
    if len(parcels)!=1:
        return None
    geometry=parcels[0].get('geometry') or {}
    points=[p for r in geometry.get('rings',[]) for p in r]
    if not points:return None
    x=(min(p[0] for p in points)+max(p[0] for p in points))/2
    y=(min(p[1] for p in points)+max(p[1] for p in points))/2
    if point_in_esri(x,y,geometry):return x,y,'parcel_bbox_center_inside_polygon'
    return points[0][0],points[0][1],'parcel_boundary_vertex_fallback'


def evaluate_real(payload, db=None, as_of=None):
    """Same gate contract plus raw site and county observations.
    Supply customer-specific evidence/permit_checks through the original keys.
    """
    if not isinstance(payload,dict):raise ValueError('payload must be an object')
    mode=payload.get('gate_mode','historical_risk')
    if mode not in {'historical_risk','approximate','confirmed'}:raise ValueError('gate_mode must be historical_risk, approximate or confirmed')
    if mode in {'historical_risk','approximate'} and payload.get('enable_screening_estimates',True) is not True:
        raise ValueError('approximate mode requires enable_screening_estimates=true')
    db=db or EvidenceDatabase()
    p=deepcopy(payload)
    if not isinstance(p.get('request'),dict):raise ValueError('request must be an object')
    if p['request'].get('search_state','VA')!='VA':raise ValueError('This prepared database is Virginia only')
    candidates=p.get('candidate_county_fips',list(db.counties))
    if not isinstance(candidates,list) or any(not isinstance(c,str) or c not in db.counties for c in candidates):
        raise ValueError('candidate_county_fips must contain known Virginia five-digit FIPS codes')
    if len(set(candidates))!=len(candidates):raise ValueError('duplicate candidate county FIPS')
    p['candidate_county_fips']=candidates
    sites=p.setdefault('sites',[])
    if not isinstance(sites,list) or any(not isinstance(s,dict) for s in sites):raise ValueError('sites must be objects')
    if any(s.get('county_fips') not in candidates for s in sites):raise ValueError('selected site outside candidate list')
    known={s['county_fips'] for s in sites}
    for fips in candidates:
        if fips not in known:
            sites.append(dict(site_id='UNRESOLVED_SITE_'+fips,county_fips=fips,state='VA',
                site_resolution_status='unresolved',permit_checklist_confirmed=False,
                site_role='unresolved_candidate_placeholder'))
    evidence=p.setdefault('evidence',[])
    if not isinstance(evidence,list):raise ValueError('evidence must be a list')
    selected_observations={}
    for site in sites:
        sid,fips=site['site_id'],site['county_fips']
        pins=site.get('parcel_ids',[])
        if not isinstance(pins,list) or any(not isinstance(pin,str) for pin in pins):raise ValueError('parcel_ids must be strings')
        records=db.permits_for(fips,set(pins)) if pins else []
        # A prior permit for the same parcel is a real observation, not necessarily
        # an approval for this request/version/project. Keep it unreviewed.
        for r in records:
            evidence.append(dict(evidence_id='PUBLIC_RECORD:'+sid+':'+r['record_id'],
                site_id=sid,county_fips=fips,power_plan_id=None,gate_id='permitting_zoning',claim_type='permit_status',
                geographic_scope='site',evidence_level='public_planning',verification_status='unreviewed',
                conditions=[],conditions_verification='unknown',
                raw_statement=r['description'],recorded_status=r['status'],recorded_case=r['case_number'],
                recorded_expiry=r['expires_at'],recorded_snapshot=r['snapshot_at'],
                applicability_to_current_request='not_verified',**_source_fields(db,r)))
        parcels=[r for r in db.parcels if r['county_fips']==fips and r['parcel_pin'] in pins]
        point=_site_point(site,parcels)
        zones=[dict(layer=z['layer'],attributes=z['attributes'],**_source_fields(db,z)) for z in db.zones
               if z['county_fips']==fips and point and point_in_esri(point[0],point[1],z['geometry'])]
        selected_observations[sid]=dict(parcel_link_method='exact_PIN' if pins else 'no_parcel_selected',
            linked_parcel_records=[dict(parcel_pin=r['parcel_pin'],attributes=r['attributes'],**_source_fields(db,r)) for r in parcels],
            permit_records=[dict(r,**_source_fields(db,r)) for r in records],
            zoning_point_observations=zones,
            spatial_point=dict(longitude=point[0],latitude=point[1],method=point[2]) if point else None,
            spatial_limitation='A sample-point zoning match is not a whole-parcel determination or permitted-use approval.')
    output=evaluate_bundle(p,as_of)
    output['data_version']=db.version
    output['request_is_example']=payload.get('request_is_example',False)
    output['real_data_connected']=True
    for result in output['site_results']:
        result['public_site_observations']=selected_observations[result['site_id']]
    for c in output['county_evidence_summary']:
        fips=c['county_fips'];records=db.permits_for(fips)
        projects=[r for r in db.projects if r['county_fips']==fips]
        project_context=[]
        for r in projects:
            engineering=[db.engineering[i] for i in r['matched_engineering_record_ids']]
            project_context.append(dict(r,**_source_fields(db,r),
                engineering_updates=[dict(e,**_source_fields(db,e)) for e in engineering],
                interpretation='Historic customer demand and transmission engineering dates; not capacity or delivery commitments for the current user.'))
        c.update(county_name=db.counties[fips]['name'],
            public_record_counts=dict(data_center_related_permits=len(records),
                by_status=dict(Counter(r['status'] for r in records)),historical_public_load_projects=len(projects)),
            public_load_project_observations=project_context,
            example_public_permits=[dict(r,**_source_fields(db,r)) for r in records[:3]],
            evidence_coverage=dict(parcel_permit_layers=fips in {'51107','51153'},
                mapped_public_load_projects=bool(projects),new_customer_capacity_confirmation=False,
                complete_project_permit_checklist=False),
            coverage_note='Downloaded permit layers cover Loudoun/Prince William; mapped load slides cover four Henrico projects. Zero matching records is not a feasibility failure.')
    output['limitations']=[
        'No public record is automatically treated as a new-customer reserved capacity or full-capacity delivery commitment.',
        'PJM Virginia engineering rows are retained, but unlocated rows are not arbitrarily assigned to a county.',
        'Public permits may concern existing buildings or other project phases; requirement applicability and conditions need review.',
        'An UNKNOWN after connecting real data means the downloaded evidence does not establish this project requirement.']
    if payload.get('enable_screening_estimates', True):
        from .screening_estimates import add_screening_estimates
        add_screening_estimates(output, payload, db)
    if mode=='historical_risk':
        from .historical_risk_gates import apply_historical_risk_gates
        apply_historical_risk_gates(output,payload,db)
    elif mode=='approximate':
        from .approximate_gates import apply_approximate_gates
        apply_approximate_gates(output,payload)
    else:
        output['gate_mode']='confirmed'
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--as-of',default=None)
    parser.add_argument('--data-dir',type=Path)
    a=parser.parse_args()
    try:
        result=evaluate_real(json.loads(a.input.read_text(encoding='utf-8')),EvidenceDatabase(a.data_dir),a.as_of)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    except (ValueError,OSError) as exc:
        parser.exit(2,'Input error: '+str(exc)+'\n')


if __name__=='__main__':main()
