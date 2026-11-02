"""Offline point lookup in a Geofabrik WGS84 water polygon shapefile.

Returns all containing water candidates without certifying lake type, OSM
object type, or extract completeness. Install the local-osm extra first.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import shapefile
from shapely.geometry import Point, mapping, shape

from enviro_data.lake_polygons import name_agreement


def lookup(path: Path, lat: float, lon: float, site_name: str = ""):
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("invalid WGS84 coordinate")
    # Check the actual source projection, rather than assume every .shp is WGS84.
    prj = path.with_suffix(".prj").read_text(encoding="utf-8")
    from rasterio.crs import CRS
    if CRS.from_wkt(prj).to_epsg() != 4326:
        raise ValueError("local lookup requires EPSG:4326")
    point = Point(lon, lat)
    features, rejected = [], []
    with shapefile.Reader(str(path), encoding="utf-8") as reader:
        fields = {field[0] for field in reader.fields[1:]}
        if not {"osm_id", "fclass", "name"} <= fields:
            raise ValueError("missing Geofabrik water attributes")
        if reader.shapeType != shapefile.POLYGON:
            raise ValueError("expected polygon layer, not waterways lines")
        # Bounding-box filtering is a scan, not a persistent spatial index.
        for item in reader.iterShapeRecords(bbox=(lon, lat, lon, lat)):
            attrs = item.record.as_dict()
            if attrs["fclass"] not in {"water", "reservoir"}:
                continue
            geom = shape(item.shape.__geo_interface__)
            if not geom.is_valid:
                rejected.append({"record_index": item.record.oid, "reason": "invalid_geometry"})
                continue
            if not geom.covers(point):
                continue
            features.append({"type": "Feature", "geometry": mapping(geom), "properties": {
                **attrs, "record_index": item.record.oid,
                "status": "candidate_water_polygon", "review_required": True,
                "point_on_boundary": not geom.contains(point),
                "name_evidence": name_agreement(site_name, {"name": attrs["name"]}),
                "waterbody_type": "reservoir" if attrs["fclass"] == "reservoir" else "unspecified_water",
                "osm_object_type": "unknown", "whole_osm_object_verified": False,
            }})
    readme = path.parent / "README"
    return {"type": "FeatureCollection", "features": features, "lookup": {
        "source": str(path.resolve()), "latitude": lat, "longitude": lon,
        "site_name": site_name, "crs": "EPSG:4326", "rejected": rejected,
        "source_readme": readme.read_text(encoding="utf-8") if readme.exists() else "",
        "license": "OpenStreetMap contributors, ODbL; retain source attribution",
        "method": "bounding box scan then point covers polygon; holes preserved",
        "limitation": "Free export loses lake/pond tags and object type; verify full geometry before metrics.",
    }}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shapefile", type=Path, required=True)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--site-name", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = lookup(args.shapefile, args.latitude, args.longitude, args.site_name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"candidates": len(result["features"]), "output": str(args.output),
                      "properties": [f["properties"] for f in result["features"]]}, ensure_ascii=False))
