"""Prepare immutable lake-QC collections from completed local lookups, offline."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from .ee_app_assets import _canonical, _ee_property_key, _primitive, _sha256


def prepare_lake_validation_assets(run_dir: Path, output_root: Path) -> Path:
    paths = [run_dir / name for name in (
        "lake_polygon_pilot.csv", "lake_polygon_pilot.geojson",
        "candidate_discovery.jsonl", "candidate_outcomes.jsonl", "selection_manifest.json",
        "run_metadata.json")]
    paths.extend(sorted((run_dir / "candidate_polygons").glob("*.geojson")))
    sources = {path.relative_to(run_dir).as_posix(): _sha256(path) for path in paths}
    release = "ee_lake_review_v1_" + hashlib.sha256(_canonical(sources)).hexdigest()[:16]
    target = output_root / release
    with paths[0].open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = {row["sample_id"] for row in rows}
    if not rows or len(ids) != len(rows):
        raise ValueError("Lake review requires unique, nonempty sample IDs")
    discovery: dict[str, list] = {sample: [] for sample in ids}
    for line in paths[2].read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["sample_id"] not in ids:
            raise ValueError("Discovery references a site outside this run")
        discovery[record["sample_id"]].append(record)

    def feature(source: dict) -> dict:
        result = copy.deepcopy(source)
        props = result["properties"]
        if props["sample_id"] not in ids:
            raise ValueError("Polygon references a site outside this run")
        result["properties"] = {_ee_property_key(key): _primitive(value)
                                for key, value in props.items()}
        result["properties"].update(app_release_id=release, review_required=True)
        return result

    points = []
    for row in rows:
        properties = {key: value if value != "" else None for key, value in row.items()}
        properties["discovery_evidence"] = discovery[row["sample_id"]]
        points.append(feature({"type": "Feature", "id": row["sample_id"],
                               "properties": properties, "geometry": {"type": "Point",
                               "coordinates": [float(row["longitude"]), float(row["latitude"])]}}))
    selected = [feature(item) for item in json.loads(paths[1].read_text(encoding="utf-8"))["features"]]
    evaluated = [feature(json.loads(path.read_text(encoding="utf-8"))) for path in paths[6:]]
    selected_keys = {(item["properties"]["sample_id"], item["properties"]["osm_type"],
                      str(item["properties"]["osm_id"])) for item in selected}
    for item in evaluated:
        props = item["properties"]
        props["selected_candidate"] = (props["sample_id"], props["osm_type"], str(props["osm_id"])) in selected_keys
    collections = {"lake_sites": points, "selected_candidates": selected, "evaluated_polygons": evaluated}
    contents = {name + ".geojson": _canonical({"type": "FeatureCollection", "features": features})
                for name, features in collections.items()}
    manifest = {"app_release_id": release, "source_checksums": sources,
                "counts": {key: len(value) for key, value in collections.items()},
                "collection_checksums": {name: hashlib.sha256(body).hexdigest() for name, body in contents.items()},
                "notice": "Frozen candidates for manual QC; no habitat identity certified. No terrain joins assumed."}
    contents["manifest.json"] = _canonical(manifest)
    # Identical reruns are allowed; altered frozen outputs are never overwritten.
    if target.exists():
        for name, body in contents.items():
            if not (target / name).exists() or (target / name).read_bytes() != body:
                raise ValueError(f"Existing immutable bundle differs: {target / name}")
        return target
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".lake-review-", dir=output_root))
    try:
        for name, body in contents.items():
            (staging / name).write_bytes(body)
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target
