"""Local HydroLAKES fallback; bbox-only scan before reading candidate polygons.

The raw global download and extracted geofiles remain under ignored data/cache.
HydroLAKES covers lakes >=10 ha, not the full small-lake target population.
"""

from __future__ import annotations
import argparse, csv, hashlib, json, logging, math, struct, time, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from enviro_data.input import load_sites
from enviro_data.lake_lookup import atomic_json
from enviro_data.lake_polygons import polygon_metrics, name_agreement
from enviro_data.site_habitat import infer_site_habitat
from enviro_data.river_sources import sha

ROOT = Path(__file__).resolve().parents[1]
URL = "https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip"


def prepare(source, output_dir, *, live=False):
    import shapefile
    from rasterio.crs import CRS
    from shapely.geometry import shape, Point

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    archive = out / "HydroLAKES_polys_v10_shp.zip"
    if not archive.exists():
        if not live:
            raise RuntimeError("HydroLAKES archive missing; opt into --live download")
        partial = archive.with_suffix(".part")
        started = time.monotonic()
        total = 0
        last_log = started
        try:
            with (
                urlopen(
                    Request(
                        URL,
                        headers={"User-Agent": "stickleback environmental research"},
                    ),
                    timeout=30,
                ) as response,
                partial.open("wb") as f,
            ):
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 1_100_000_000 or time.monotonic() - started > 600:
                        raise ValueError("HydroLAKES download bound exceeded")
                    f.write(chunk)
                    if time.monotonic() - last_log > 10:
                        logging.info("downloaded_MB=%.1f", total / 1e6)
                        last_log = time.monotonic()
            partial.replace(archive)
        finally:
            if partial.exists():
                partial.unlink()
    logging.info("archive available size_MB=%.1f", archive.stat().st_size / 1e6)
    directory = out / "source"
    directory.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if Path(member.filename).suffix.lower() in {".shp", ".shx", ".dbf", ".prj"}:
                dest = directory / Path(member.filename).name
                if not dest.exists():
                    if member.file_size > 4_000_000_000:
                        raise ValueError("uncompressed member bound exceeded")
                    logging.info("extracting=%s", dest.name)
                    with z.open(member) as data, dest.open("wb") as f:
                        while chunk := data.read(1024 * 1024):
                            f.write(chunk)
    path = next(directory.glob("*.shp"))
    if CRS.from_wkt(path.with_suffix(".prj").read_text()).to_epsg() != 4326:
        raise ValueError("HydroLAKES source CRS mismatch")
    records = [
        r
        for r in load_sites(source, strict=True).records
        if infer_site_habitat(r.population_name, r.ecotype).working_waterbody_type
        == "lake"
        and r.ecotype == "freshwater"
    ]
    grid = {}
    for i, r in enumerate(records):
        grid.setdefault((math.floor(r.longitude), math.floor(r.latitude)), []).append(i)
    matches = {}
    rejected = []
    count = 0
    with shapefile.Reader(str(path)) as reader, path.open("rb") as scan:
        scan.seek(100)
        index = 0
        while header := scan.read(8):
            _, words = struct.unpack(">2i", header)
            end = scan.tell() + words * 2
            prefix = scan.read(min(36, words * 2))
            candidates = []
            if len(prefix) == 36 and struct.unpack("<i", prefix[:4])[0] in {5, 15, 25}:
                x0, y0, x1, y1 = struct.unpack("<4d", prefix[4:])
                if (x1 - x0) * (y1 - y0) > 1000:
                    candidate_indices = range(len(records))
                else:
                    candidate_indices = [
                        i
                        for x in range(math.floor(x0), math.floor(x1) + 1)
                        for y in range(math.floor(y0), math.floor(y1) + 1)
                        for i in grid.get((x, y), [])
                    ]
                candidates = [
                    records[i]
                    for i in candidate_indices
                    if x0 <= records[i].longitude <= x1
                    and y0 <= records[i].latitude <= y1
                ]
            if candidates:
                geometry = reader.shape(index).__geo_interface__
                geom = shape(geometry)
                if not geom.is_valid:
                    rejected.append(
                        {"record_index": index, "reason": "invalid_polygon"}
                    )
                else:
                    for record in candidates:
                        point = Point(record.longitude, record.latitude)
                        if not geom.covers(point):
                            continue
                        props = reader.record(index).as_dict()
                        groups = (
                            [geometry["coordinates"]]
                            if geometry["type"] == "Polygon"
                            else geometry["coordinates"]
                        )
                        metrics = polygon_metrics(groups)
                        evidence = name_agreement(
                            record.population_name, {"name": props.get("Lake_name", "")}
                        )
                        result = {
                            "sample_id": record.sample_id,
                            "status": "candidate_polygon",
                            "source": "HydroLAKES v1.0",
                            "hylak_id": (
                                props["Hylak_id"]
                                if "Hylak_id" in props
                                else props.get("HYLAK_ID")
                            ),
                            "source_lake_type_code": props.get("Lake_type"),
                            "name_evidence": evidence.replace(
                                "osm_unnamed", "source_unnamed"
                            ),
                            "point_inside_polygon": geom.contains(point),
                            "point_on_boundary": not geom.contains(point),
                            "review_required": True,
                            "minimum_source_lake_area_ha": 10,
                            **metrics,
                        }
                        matches.setdefault(record.sample_id, []).append(
                            {
                                "result": result,
                                "feature": {
                                    "type": "Feature",
                                    "geometry": geometry,
                                    "properties": result,
                                },
                            }
                        )
            count += 1
            index += 1
            scan.seek(end)
            if count % 200000 == 0:
                logging.info("records_scanned=%d matched_sites=%d", count, len(matches))
    checksum = sha(archive)
    results = {}
    features = []
    for sid, items in matches.items():
        items.sort(
            key=lambda item: (
                item["result"]["lake_area_m2"],
                str(item["result"]["hylak_id"]),
            )
        )
        selected = items[0]
        selected["result"].update(
            ambiguity_flag=len(items) > 1,
            sha256=checksum,
            source_url=URL,
            source_version="v1.0",
            coordinate_containment_required=True,
        )
        results[sid] = selected["result"]
        features.append(selected["feature"])
    atomic_json(out / "lake_results.json", results)
    atomic_json(
        out / "lake_polygons.geojson",
        {"type": "FeatureCollection", "features": features},
    )
    metadata = {
        "source": URL,
        "archive_sha256": checksum,
        "version": "v1.0",
        "records_scanned": count,
        "eligible_sites": len(records),
        "candidate_polygon_sites": len(results),
        "rejected": rejected,
        "selection": "original point covered by polygon; never snapped; smallest containing candidate if multiple, ambiguity retained",
        "area_method": "spherical WGS84; holes subtracted",
        "shoreline_method": "great-circle ring segments including islands; raw source resolution",
    }
    atomic_json(out / "provenance.json", metadata)
    return metadata


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT / "site_overview_v1_clean.csv")
    p.add_argument("--output-dir", type=Path, default=ROOT / "data/cache/hydrolakes")
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(json.dumps(prepare(a.input, a.output_dir, live=a.live), indent=2))
