from dataclasses import dataclass
@dataclass(frozen=True)
class CatchmentElevationMeanResult:
    elevation_mean_m: float | None
    status: str
def catchment_elevation_mean(values, *, marine=False):
    if marine: return CatchmentElevationMeanResult(None, "not_applicable_marine")
    vals = [float(v) for v in values if v is not None]
    return CatchmentElevationMeanResult(sum(vals)/len(vals), "ok") if vals else CatchmentElevationMeanResult(None, "no_valid_dem_data")
