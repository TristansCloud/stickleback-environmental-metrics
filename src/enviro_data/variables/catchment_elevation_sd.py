from dataclasses import dataclass
from math import sqrt
@dataclass(frozen=True)
class CatchmentElevationSdResult:
    elevation_sd_m: float | None
    status: str
def catchment_elevation_sd(values, *, marine=False):
    if marine: return CatchmentElevationSdResult(None, "not_applicable_marine")
    vals = [float(v) for v in values if v is not None]
    if not vals: return CatchmentElevationSdResult(None, "no_valid_dem_data")
    mean = sum(vals)/len(vals)
    return CatchmentElevationSdResult(sqrt(sum((v-mean)**2 for v in vals)/len(vals)), "ok")
