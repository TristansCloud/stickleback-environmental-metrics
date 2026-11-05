"""Upload a verified combined site-metrics release privately to Earth Engine."""
import argparse
import json
from pathlib import Path
import time
import ee


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--project',required=True)
    args=p.parse_args()
    features=json.loads((args.bundle/'site_metrics.geojson').read_bytes())['features']
    digest=args.bundle.name
    assert len(features)==599 and len({f['properties']['sample_id'] for f in features})==599
    assert all(f['properties']['shoreline_release']==digest for f in features)
    ee.Initialize(project=args.project)
    asset=f'projects/{args.project}/assets/stickleback_validation/site_metrics_v1_{digest}'
    record=args.bundle/'upload.json'
    if record.exists():
        prior=json.loads(record.read_bytes());assert prior['asset']==asset
        task_id=prior['task']
    else:
        converted=[ee.Feature(ee.Geometry.Point(f['geometry']['coordinates']),
                              {k:v for k,v in f['properties'].items() if v is not None}) for f in features]
        task=ee.batch.Export.table.toAsset(collection=ee.FeatureCollection(converted),
                                          description=f'site_metrics_{digest}',assetId=asset)
        task.start();task_id=task.id
        record.write_text(json.dumps({'asset':asset,'task':task_id}),encoding='utf-8')
    print(asset,task_id,flush=True)
    for _ in range(60):
        status=ee.data.getTaskStatus(task_id)[0]
        if status['state']=='COMPLETED':break
        if status['state'] not in {'READY','RUNNING'}:raise RuntimeError(status)
        time.sleep(10)
    else:raise TimeoutError('Export still running; resume using the same bundle')
    fc=ee.FeatureCollection(asset)
    checks=ee.Dictionary({'rows':fc.size(),'sites':fc.aggregate_count_distinct('sample_id'),
                          'release':fc.filter(ee.Filter.eq('shoreline_release',digest)).size(),
                          'statuses':fc.aggregate_histogram('shoreline_elevation_status')}).getInfo()
    assert checks['rows']==checks['sites']==checks['release']==599,checks
    print('VERIFIED',json.dumps(checks),flush=True)


if __name__=='__main__':main()
