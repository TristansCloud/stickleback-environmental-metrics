from dataclasses import dataclass
@dataclass(frozen=True)
class NearWaterReliefResult:
    relief_m: float | None
    status: str
def near_water_relief(sample_elevation_m, water_elevation_m, *, water_found=True):
    if not water_found: return NearWaterReliefResult(None, "no_near_water")
    if sample_elevation_m is None or water_elevation_m is None: return NearWaterReliefResult(None, "insufficient_data")
    return NearWaterReliefResult(abs(float(sample_elevation_m)-float(water_elevation_m)), "ok")
