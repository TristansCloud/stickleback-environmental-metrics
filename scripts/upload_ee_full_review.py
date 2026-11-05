"""Upload privately, verify, then explicitly share a frozen full-review release.

The default prints an offline plan. --upload starts new exports without replacing
assets. --verify checks live counts, release IDs and upload metadata. --share-public
requires --verify and only shares this exact release's four tables. It does not
publish the App or change project IAM. Prior EE authentication is required.
"""
import argparse
import json
from pathlib import Path
from enviro_data.ee_app_assets import _sha256


def load_bundle(path):
    manifest = json.loads((path / 'manifest.json').read_text(encoding="utf-8"))
    if manifest.get('schema_version') != 'ee_full_review_v1' or manifest['counts'].get('sites') != 599:
        raise ValueError('Not a complete supported 599-site review release')
    collections = {}
    for name, checksum in manifest['collection_checksums'].items():
        if Path(name).name != name or _sha256(path / name) != checksum:
            raise ValueError(f'Frozen collection checksum mismatch: {name}')
        collection = json.loads((path / name).read_text(encoding="utf-8"))
        if len(collection['features']) != manifest['counts'][Path(name).stem]:
            raise ValueError(f'Collection count mismatch: {name}')
        if any(f['properties'].get('app_release_id') != manifest['app_release_id'] for f in collection['features']):
            raise ValueError('Mixed release collection')
        collections[Path(name).stem] = collection
    if set(collections) != {'sites', 'lake_candidates', 'river_candidates', 'shoreline_samples'}:
        raise ValueError('Unexpected release collections')
    return manifest, collections


def verify_release(ee, root, manifest, bundle):
    """Fail before sharing anything if any of the four tables is incomplete."""
    expected_tasks = json.loads((bundle / 'upload_tasks.json').read_text(encoding="utf-8"))
    for name, count in manifest['counts'].items():
        record = expected_tasks['tables'][name]
        if record['asset'] != root + '/' + name:
            raise ValueError('Upload record names a different destination')
        task = ee.data.getTaskStatus(record['task_id'])[0]
        if task['state'] != 'COMPLETED':
            raise ValueError(f'{name} export is {task["state"]}; wait or inspect the task error')
        asset = root + '/' + name
        fc = ee.FeatureCollection(asset)
        actual = ee.Dictionary({'count': fc.size(), 'same_release': fc.filter(
            ee.Filter.eq('app_release_id', manifest['app_release_id'])).size()}).getInfo()
        if actual != {'count': count, 'same_release': count}:
            raise ValueError(f'Cloud collection differs: {asset}: {actual}')
    return expected_tasks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--asset-parent', required=True)
    parser.add_argument('--upload', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--share-public', action='store_true')
    args = parser.parse_args()
    if args.upload and args.verify:
        parser.error('Upload and verify are separate steps; exports must finish first')
    if args.share_public and not args.verify:
        parser.error('--share-public requires --verify')
    manifest, collections = load_bundle(args.bundle)
    root = args.asset_parent.rstrip('/') + '/' + manifest['app_release_id']
    if not args.upload and not args.verify:
        print(json.dumps({'root': root, 'counts': manifest['counts'], 'network': False,
                          'next': 'Authenticate Earth Engine, then use --upload'}, indent=2))
        return
    import ee
    ee.Initialize(project=args.project)
    if args.upload:
        if (args.bundle / 'upload_tasks.json').exists():
            raise ValueError('Upload record already exists; inspect exports instead of repeating')
        existing = ee.data.listAssets({'parent': args.asset_parent}).get('assets', [])
        if any(a.get('name') == root or a.get('id') == root for a in existing):
            raise ValueError('Immutable release already exists; do not overwrite or repeat partial exports')
        ee.data.createAsset({'type': 'FOLDER'}, root)
        record = {'root': root, 'release': manifest['app_release_id'],
                  'manifest_sha256': _sha256(args.bundle / 'manifest.json'), 'tables': {}}
        for name, collection in collections.items():
            # GeoJSON straight edges are retained; do not replace with geodesic arcs.
            features = [ee.Feature(
                ee.Geometry(f['geometry'], 'EPSG:4326',
                            geodesic=None if f['geometry']['type'] == 'Point' else False),
                f['properties'])
                        for f in collection['features']]
            task = ee.batch.Export.table.toAsset(collection=ee.FeatureCollection(features),
                description=name + '_' + manifest['app_release_id'], assetId=root + '/' + name)
            task.start()
            record['tables'][name] = {'task_id': task.id, 'asset': root + '/' + name}
            (args.bundle / 'upload_tasks.json').write_text(json.dumps(record, indent=2))
            print(json.dumps(record['tables'][name]))
        print('Exports started privately. After all complete, run --verify.')
    else:
        record = verify_release(ee, root, manifest, args.bundle)
        if record['manifest_sha256'] != _sha256(args.bundle / 'manifest.json'):
            raise ValueError('Upload record checksum differs')
        print('Verified all 599 sites and all evidence collections.')
        if args.share_public:
            for name in collections:
                asset = root + '/' + name
                acl = ee.data.getAssetAcl(asset)
                acl['all_users_can_read'] = True
                ee.data.setAssetAcl(asset, json.dumps(acl))
                if not ee.data.getAssetAcl(asset).get('all_users_can_read'):
                    raise ValueError(f'Public-read verification failed: {asset}')
                print('Public read verified:', asset)
            print('Publish the configured App in the Code Editor, then test signed out.')


if __name__ == '__main__':
    main()
