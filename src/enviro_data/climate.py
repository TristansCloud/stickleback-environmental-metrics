"""Extract monthly climate values from user-supplied local rasters.

Rasterio is intentionally an optional dependency.  No data are downloaded; callers
must provide paths (and may inject a raster opener for tests or another local backend).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
import math

VARIABLES = ("tmin", "tmax", "precip")

@dataclass(frozen=True)
class RasterProvenance:
    path: str
    variable: str
    source_crs: Optional[str]
    nodata: Any
    sampled: bool
    status: str

@dataclass(frozen=True)
class ClimateMonth:
    month: int
    tmin: Optional[float]
    tmax: Optional[float]
    precip: Optional[float]
    status: str
    provenance: tuple[RasterProvenance, ...]

@dataclass(frozen=True)
class ClimateResult:
    latitude: float
    longitude: float
    months: tuple[ClimateMonth, ...]
    status: str

def _default_open(path: str):
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("Raster climate extraction requires rasterio; install it or inject opener") from exc
    return rasterio.open(path)

class ClimateExtractor:
    """Sample one-band local rasters at a geographic point.

    ``rasters`` maps month numbers to mappings with keys ``tmin``, ``tmax`` and
    ``precip``. Values are local paths. Missing variables/paths produce null values,
    never invented zeros. ``ecotype='marine'`` returns explicit not-applicable rows.
    """
    def __init__(self, rasters: Mapping[int, Mapping[str, str]], opener: Optional[Callable] = None):
        self.rasters = rasters
        self.opener = opener or _default_open

    def extract(self, latitude: float, longitude: float, *, ecotype: Optional[str] = None) -> ClimateResult:
        marine = (ecotype or "").strip().lower() in {"marine", "ocean", "pelagic", "coastal_marine"}
        rows = []
        for month in range(1, 13):
            sources = self.rasters.get(month, {})
            values = {}
            provenance = []
            if marine:
                rows.append(ClimateMonth(month, None, None, None, "not_applicable_marine", ()))
                continue
            for variable in VARIABLES:
                path = sources.get(variable)
                if not path:
                    values[variable] = None
                    continue
                try:
                    value, prov = self._sample(path, variable, latitude, longitude)
                except (FileNotFoundError, OSError) as exc:
                    value = None
                    prov = RasterProvenance(str(path), variable, None, None, False, "file_unavailable")
                provenance.append(prov)
                values[variable] = value
            status = "ok" if any(v is not None for v in values.values()) else "no_valid_data"
            rows.append(ClimateMonth(month, values.get("tmin"), values.get("tmax"), values.get("precip"), status, tuple(provenance)))
        overall = "not_applicable_marine" if marine else ("ok" if any(r.status == "ok" for r in rows) else "no_valid_data")
        return ClimateResult(float(latitude), float(longitude), tuple(rows), overall)

    def _sample(self, path, variable, latitude, longitude):
        with self.opener(str(path)) as raster:
            # Rasterio's sample expects x,y in the raster CRS; transform only when needed.
            x, y = longitude, latitude
            if getattr(raster, "crs", None) and str(raster.crs).upper() not in {"EPSG:4326", "OGC:CRS84"}:
                try:
                    from rasterio.warp import transform
                    x, y = transform("EPSG:4326", raster.crs, [longitude], [latitude])
                    x, y = x[0], y[0]
                except ImportError as exc:
                    raise RuntimeError("Non-WGS84 raster requires rasterio.warp") from exc
            raw = next(iter(raster.sample([(x, y)])))
            value = raw[0] if hasattr(raw, "__len__") else raw
            nodata = getattr(raster, "nodata", None)
            valid = value is not None and not (isinstance(value, float) and math.isnan(value)) and value != nodata
            result = float(value) if valid else None
            status = "sampled" if valid else "nodata"
            prov = RasterProvenance(str(path), variable, str(getattr(raster, "crs", "")) or None, nodata, valid, status)
            return result, prov
