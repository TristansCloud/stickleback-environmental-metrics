"""Map every input site to Geofabrik country extract boundaries, offline.

Fetch https://download.geofabrik.de/index-v1.json separately and pass --index.
Overlapping extract bounds are retained; an unmatched point fails the plan.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

from shapely.geometry import Point, shape


def plan(source: Path, index: Path):
    catalog = json.loads(index.read_text(encoding="utf-8"))
    regions = [(f["properties"], shape(f["geometry"])) for f in catalog["features"]
               if f["properties"].get("iso3166-1:alpha2")]
    properties = {p["id"]: p for p, _ in regions}
    with source.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    counts, assignments, uncovered, overlaps = Counter(), [], [], []
    for row in rows:
        point = Point(float(row["Longitude"]), float(row["Latitude"]))
        matches = [p["id"] for p, geometry in regions if geometry.covers(point)]
        if not matches:
            uncovered.append(row)
            continue
        counts.update(matches)
        assignment = {"sample_id": row["sample_id"], "regions": matches}
        assignments.append(assignment)
        if len(matches) > 1:
            overlaps.append(assignment)
    return {
        "input": str(source.resolve()), "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "index_url": "https://download.geofabrik.de/index-v1.json",
        "index_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
        "site_count": len(rows), "method": "point covered by country extract polygon; all overlaps retained",
        "regions": [{"id": key, "name": properties[key]["name"], "site_count": counts[key],
                     "urls": properties[key]["urls"]} for key in sorted(counts)],
        "uncovered": uncovered, "overlaps": overlaps, "assignments": assignments,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("site_overview_v1_clean.csv"))
    parser.add_argument("--index", type=Path, default=Path("data/cache/geofabrik/index-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("data/cache/geofabrik/study_coverage.json"))
    args = parser.parse_args()
    result = plan(args.input, args.index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"sites": result["site_count"], "regions": len(result["regions"]),
                      "uncovered": len(result["uncovered"]), "overlaps": result["overlaps"]}))
    if result["uncovered"]:
        raise SystemExit("Some sites are outside country extract boundaries; review coverage before downloading.")
