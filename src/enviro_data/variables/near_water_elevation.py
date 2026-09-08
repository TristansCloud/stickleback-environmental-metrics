from dataclasses import dataclass
@dataclass(frozen=True)
class NearWaterElevationResult:
    elevation_m: float | None
    status: str
def near_water_elevation(value_m, *, water_found=True, nodata=None):
    if not water_found: return NearWaterElevationResult(None, "no_near_water")
    if value_m is None or value_m == nodata: return NearWaterElevationResult(None, "no_valid_dem_data")
    return NearWaterElevationResult(float(value_m), "ok")
