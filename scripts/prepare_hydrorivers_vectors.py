"""Download official regional HydroRIVERS and retain only nearby pilot reaches."""

from __future__ import annotations
import argparse, csv, hashlib, json, logging, math, time, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from enviro_data.lake_lookup import atomic_json
from enviro_data.river_sources import sha

ROOT = Path(__file__).resolve().parents[1]


def prepare(source, output_dir, *, regions=("eu", "na"), live=False):
    import shapefile
    from rasterio.crs import CRS

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with Path(source).open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not 1 <= len(rows) <= 100:
        raise ValueError("at most 100 river points")
    boxes = []
    for r in rows:
        x, y = float(r["Longitude"]), float(r["Latitude"])
        dx = 500 / (111195 * math.cos(math.radians(y)))
        dy = 500 / 111195
        boxes.append((x - dx, y - dy, x + dx, y + dy))
    features = []
    sources = []
    for region in regions:
        if region not in {"eu", "na", "gr", "as", "si", "ar"}:
            raise ValueError("unsupported regional code")
        url = f"https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_{region}_shp.zip"
        archive = out / f"HydroRIVERS_v10_{region}_shp.zip"
        if not archive.exists():
            if not live:
                raise RuntimeError(f"cache missing: {archive}")
            temp = archive.with_suffix(".part")
            started = time.monotonic()
            total = 0
            try:
                with (
                    urlopen(
                        Request(
                            url,
                            headers={
                                "User-Agent": "stickleback-environmental-metrics research"
                            },
                        ),
                        timeout=20,
                    ) as response,
                    temp.open("wb") as target,
                ):
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > 110_000_000 or time.monotonic() - started > 120:
                            raise ValueError("regional download bound exceeded")
                        target.write(chunk)
                temp.replace(archive)
            finally:
                if temp.exists():
                    temp.unlink()
        sources.append(
            {
                "region": region,
                "url": url,
                "sha256": sha(archive),
                "version": "v1.0",
                "attribution": "Lehner & Grill 2013 / HydroSHEDS HydroRIVERS",
            }
        )
        directory = out / region
        directory.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if Path(member.filename).suffix.lower() in {
                    ".shp",
                    ".shx",
                    ".dbf",
                    ".prj",
                }:
                    dest = directory / Path(member.filename).name
                    if not dest.exists():
                        if member.file_size > 1_500_000_000:
                            raise ValueError("uncompressed source too large")
                        with z.open(member) as data, dest.open("wb") as f:
                            while chunk := data.read(1024 * 1024):
                                f.write(chunk)
        path = next(directory.glob("*.shp"))
        if CRS.from_wkt(path.with_suffix(".prj").read_text()).to_epsg() != 4326:
            raise ValueError("HydroRIVERS projection is not WGS84")
        count = 0
        with shapefile.Reader(str(path)) as reader:
            for geom in reader.iterShapes():
                x0, y0, x1, y1 = geom.bbox
                if not any(
                    x0 <= b[2] and x1 >= b[0] and y0 <= b[3] and y1 >= b[1]
                    for b in boxes
                ):
                    continue
                properties = reader.record(geom.oid).as_dict()
                features.append(
                    {
                        "type": "Feature",
                        "id": f"HYRIV/{properties['HYRIV_ID']}",
                        "properties": properties,
                        "geometry": geom.__geo_interface__,
                    }
                )
                count += 1
        logging.info("region=%s nearby_reaches=%d", region, count)
        atomic_json(
            out / "nearby_reaches.geojson",
            {"type": "FeatureCollection", "features": features},
        )
        atomic_json(
            out / "sources.json",
            {
                "input_sha256": sha(source),
                "sources": sources,
                "candidate_features": len(features),
            },
        )
    return {
        "candidate_features": len(features),
        "regions": list(regions),
        "output": str(out / "nearby_reaches.geojson"),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data/habitat_pilots/stream_pilot_sites_v1.csv",
    )
    p.add_argument("--output-dir", type=Path, default=ROOT / "data/cache/hydrorivers")
    p.add_argument("--regions", nargs="+", default=["eu", "na"])
    p.add_argument("--live", action="store_true")
    a = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    print(
        json.dumps(
            prepare(a.input, a.output_dir, regions=a.regions, live=a.live), indent=2
        )
    )
