from dataclasses import dataclass
@dataclass(frozen=True)
class CatchmentElevationReliefResult:
    relief_m: float | None
    status: str
def catchment_elevation_relief(values, *, marine=False):
    if marine: return CatchmentElevationReliefResult(None, "not_applicable_marine")
    vals = [float(v) for v in values if v is not None]
    return CatchmentElevationReliefResult(max(vals)-min(vals), "ok") if vals else CatchmentElevationReliefResult(None, "no_valid_dem_data")
