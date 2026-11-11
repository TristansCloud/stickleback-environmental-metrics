"""Small cached public Copernicus GLO-90 tiles; no whole-global DEM download."""

from __future__ import annotations
import math
from pathlib import Path
from urllib.request import Request
from .osm_http import bounded_urlopen
from .river_sources import sha
from .river_snapping import number


def tile_identity(lon, lat):
    x, y = math.floor(lon), math.floor(lat)
    stem = f"Copernicus_DSM_COG_30_{'N' if y>=0 else 'S'}{abs(y):02d}_00_{'E' if x>=0 else 'W'}{abs(x):03d}_00_DEM"
    return stem, f"https://copernicus-dem-90m.s3.amazonaws.com/{stem}/{stem}.tif"


def sample_coordinates(coordinates, cache_dir, *, live=False):
    import rasterio

    groups = {}
    for index, (lon, lat) in enumerate(coordinates):
        groups.setdefault(tile_identity(lon, lat), []).append((index, (lon, lat)))
    if len(groups) > 20:
        raise ValueError("single lake request exceeds 20 DEM tiles")
    values = [None] * len(coordinates)
    sources = []
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for (stem, url), members in groups.items():
        path = cache_dir / f"{stem}.tif"
        try:
            if not path.exists():
                if not live:
                    raise RuntimeError("local DEM tile missing; live download disabled")
                with bounded_urlopen(Request(url), timeout=25) as response:
                    raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise ValueError("tile exceeds 8 MB pilot bound")
                temp = path.with_suffix(".part")
                temp.write_bytes(raw)
                with rasterio.open(temp) as ds:
                    if ds.crs != rasterio.crs.CRS.from_epsg(4326):
                        raise ValueError("DEM CRS mismatch")
                temp.replace(path)
            with rasterio.open(path) as ds:
                samples = ds.sample([p for _, p in members], masked=True)
                for (index, _), sample in zip(members, samples):
                    value = sample[0]
                    values[index] = (
                        None if bool(getattr(value, "mask", False)) else number(value)
                    )
            sources.append(
                {
                    "source": "Copernicus DEM GLO-90 2021 DSM",
                    "url": url,
                    "path": str(path),
                    "sha256": sha(path),
                    "unit": "m",
                    "vertical_reference": "EGM2008",
                    "method": "nearest native raster cell; masked/nodata preserved",
                    "status": "ok",
                }
            )
        except Exception as error:
            sources.append(
                {
                    "source": "Copernicus DEM GLO-90 2021 DSM",
                    "url": url,
                    "status": "retrieval_failed",
                    "error": str(error),
                }
            )
    return values, sources
