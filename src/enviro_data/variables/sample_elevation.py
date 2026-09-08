from dataclasses import dataclass
@dataclass(frozen=True)
class ElevationResult:
    elevation_m: float | None
    status: str
def sample_elevation(value_m, *, nodata=None, marine=False):
    if marine: return ElevationResult(None, "not_applicable_marine")
    if value_m is None or value_m == nodata: return ElevationResult(None, "no_valid_dem_data")
    return ElevationResult(float(value_m), "ok")
