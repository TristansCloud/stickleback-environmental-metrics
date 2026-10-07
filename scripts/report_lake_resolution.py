"""Report shoreline resolution sensitivity from cached pilot GeoJSON."""
import argparse
import csv
import json
from pathlib import Path

from enviro_data.lake_polygons import resolution_sensitivity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/lake_pilot/lake_polygon_pilot.geojson"))
    parser.add_argument("--output", type=Path, default=Path("data/lake_pilot/resolution_sensitivity.json"))
    args = parser.parse_args()
    features = json.loads(args.input.read_text())["features"]
    with args.input.with_name("lake_polygon_pilot.csv").open(newline="", encoding="utf-8") as handle:
        samples = {r["sample_id"]: r for r in csv.DictReader(handle)}
    results = []
    for feature in features:
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        # The sample coordinates are recorded in the pilot CSV, while the
        # feature itself carries the associated stable sample ID.
        row = samples[feature["properties"]["sample_id"]]
        results.append({"sample_id": row["sample_id"], "osm_id": feature["id"],
                        "resolutions": resolution_sensitivity(polygons, float(row["longitude"]), float(row["latitude"]))})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"method": "Douglas-Peucker in local metres per ring; island shores included; reject sample exclusion, collapsed rings, displaced island anchors, or area change over 1%", "results": results}, indent=2))
    print(f"reported {len(results)} cached polygons to {args.output}")


if __name__ == "__main__":
    main()
