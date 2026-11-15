"""Refresh all native-cell shoreline bands using the selected OSM lake polygons."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from enviro_data.shoreline_full_band import collect, cache_key, GeometryBudgetError, VERSION


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--regions',type=Path,required=True)
    p.add_argument('--base-metrics',type=Path,required=True)
    p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cell-budget',type=int,default=1_000_000)
    p.add_argument('--sample-id',action='append',help='Optional smoke-test subset')
    p.add_argument('--live',action='store_true')
    args=p.parse_args()
    if args.cell_budget<=0:p.error('cell budget must be positive')
    args.output.mkdir(parents=True,exist_ok=True)
    raw=args.regions.read_bytes();base=args.base_metrics.read_bytes()
    regions=[f for f in json.loads(raw)['features'] if f['properties']['method']=='lake_polygon_max']
    selected=set(args.sample_id or [])
    records={}
    for i,feature in enumerate(regions):
        sid=feature['properties']['sample_id']
        if selected and sid not in selected:continue
        key=cache_key(feature,args.cell_budget)
        path=args.output/(sid+'_'+key[:16]+'.json')
        prior=json.loads(path.read_bytes()) if path.exists() else None
        if prior and prior.get('cache_key')==key and prior['shoreline_elevation_status']!='source_tiles_incomplete':
            record=prior
        else:
            try:
                record=collect(feature,args.cache,args.live,args.cell_budget)
            except GeometryBudgetError as error:
                record={'shoreline_elevation_status':'geometry_or_cell_budget_exceeded','has_shoreline_profile':False,'error':str(error)}
            except Exception as error:
                record={'shoreline_elevation_status':'processing_failed','has_shoreline_profile':False,'error':str(error)}
            record.update(sample_id=sid,cache_key=key,polygon_id=feature['properties']['polygon_id'],polygon_source=feature['properties']['polygon_source'])
            path.write_text(json.dumps(record,indent=2),encoding='utf-8')
        records[sid]=record
        print(f"{i+1}/{len(regions)} {sid} {record['shoreline_elevation_status']} cells="+
              '/'.join(str(record.get(f'shore_{r}m_cell_count',0)) for r in [50,100,250]),flush=True)
    identity={'regions_sha256':hashlib.sha256(raw).hexdigest(),'base_metrics_sha256':hashlib.sha256(base).hexdigest(),
              'method':'all_valid_native_cell_centres','version':VERSION,'cell_budget':args.cell_budget,
              'record_hashes':{k:hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest() for k,v in sorted(records.items())}}
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    output=json.loads(base)
    assert len(output['features'])==599
    for feature in output['features']:
        props=feature['properties'];sid=props['sample_id'];record=records.get(sid)
        if record:
            properties={k:v for k,v in record.items() if k.startswith(('shore_','shoreline_','lake_surface_')) or k=='has_shoreline_profile'}
            properties.update(shoreline_sources_json=json.dumps(record.get('sources',[]),separators=(',',':')),
                              shoreline_error=record.get('error') or json.dumps(record.get('errors',[])),
                              shoreline_polygon_id=record['polygon_id'],shoreline_polygon_source=record['polygon_source'])
        else:
            status='not_applicable' if props['working_waterbody_type']!='lake' else 'missing_lake_polygon' if not props['has_lake_polygon'] else 'not_collected'
            properties={'shoreline_elevation_status':status,'has_shoreline_profile':False}
        props.update(properties,shoreline_release=digest)
    target=args.output/digest;target.mkdir(exist_ok=True)
    (target/'manifest.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
    (target/'site_metrics.geojson').write_text(json.dumps(output,ensure_ascii=False),encoding='utf-8')
    fields=list(dict.fromkeys(k for f in output['features'] for k in f['properties']))
    with (target/'site_metrics.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fields);writer.writeheader();writer.writerows(f['properties'] for f in output['features'])
    print('RESULT',target,Counter(f['properties']['shoreline_elevation_status'] for f in output['features']),flush=True)


if __name__=='__main__':main()
