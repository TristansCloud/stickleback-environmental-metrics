"""Upload a prepared immutable lake-review release as private EE table assets.

Requires the earth-engine optional dependency and prior Earth Engine authentication.
Does not publish an App, alter ACLs, or advance the environmental-pilot registry.
"""
import argparse
import json
from pathlib import Path

from enviro_data.ee_app_assets import _sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--asset-parent", required=True,
                        help="Existing private EE asset folder; a new immutable release folder is created beneath it")
    args = parser.parse_args()
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    collections = {}
    for name, checksum in manifest["collection_checksums"].items():
        path = args.bundle / name
        if _sha256(path) != checksum:
            raise ValueError(f"Frozen collection checksum mismatch: {path}")
        collections[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    import ee
    ee.Initialize(project=args.project)
    root = args.asset_parent.rstrip("/") + "/" + manifest["app_release_id"]
    # Listing the parent checks access and avoids catching arbitrary API errors as 'missing'.
    existing = ee.data.listAssets({"parent": args.asset_parent}).get("assets", [])
    if any(asset.get("name") == root or asset.get("id") == root for asset in existing):
        raise ValueError(f"Immutable release already exists; inspect its tasks rather than overwrite: {root}")
    ee.data.createAsset({"type": "FOLDER"}, root)
    for name, collection in collections.items():
        task = ee.batch.Export.table.toAsset(collection=ee.FeatureCollection(collection),
                                             description=name + "_" + manifest["app_release_id"],
                                             assetId=root + "/" + name)
        task.start()
        print(json.dumps({"asset": root + "/" + name, "task_id": task.id}))
    print("Wait for all three tasks to complete; then configure ee_lake_review_app.js ROOT:", root)


if __name__ == "__main__":
    main()
