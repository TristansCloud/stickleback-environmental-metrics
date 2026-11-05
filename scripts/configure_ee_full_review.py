"""Write a configured App copy from a prepared, checksum-verified release."""
import argparse
import json
import re
from pathlib import Path
from enviro_data.ee_app_assets import _sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--asset-parent', required=True)
    parser.add_argument('--merit-asset', help='Optional verified MERIT maxima table')
    parser.add_argument('--lookup-asset', help='Optional verified closest-water overlay asset')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.bundle / 'manifest.json').read_text(encoding="utf-8"))
    for name, checksum in manifest['collection_checksums'].items():
        if Path(name).name != name or _sha256(args.bundle / name) != checksum:
            raise ValueError('Collection checksum mismatch')
    parent = args.asset_parent.rstrip('/')
    if not re.fullmatch(r'projects/[A-Za-z0-9_-]+/assets/[A-Za-z0-9_/-]+', parent):
        raise ValueError('Expected a projects/PROJECT/assets/FOLDER asset parent')
    root = parent + '/' + manifest['app_release_id']
    template = Path(__file__).resolve().parents[1] / 'apps/earth_engine_validation/ee_full_review_app.js'
    app = template.read_text(encoding="utf-8").replace("'REPLACE_WITH_FULL_REVIEW_ASSET_ROOT'", json.dumps(root))
    if args.lookup_asset:
        if not re.fullmatch(r"projects/[A-Za-z0-9_-]+/assets/[A-Za-z0-9_/-]+", args.lookup_asset):
            parser.error("Expected a projects/PROJECT/assets/… lookup asset")
        app = app.replace("'REPLACE_WITH_LOOKUP_ASSET'", json.dumps(args.lookup_asset))
    if args.merit_asset:
        if not re.fullmatch(r"projects/[A-Za-z0-9_-]+/assets/[A-Za-z0-9_/-]+", args.merit_asset):
            parser.error("Expected a projects/PROJECT/assets/… MERIT asset")
        app = app.replace("'REPLACE_WITH_MERIT_MAXIMA_ASSET'", json.dumps(args.merit_asset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(app, encoding="utf-8")
    print(args.output)
    print('Asset root:', root)


if __name__ == '__main__':
    main()
