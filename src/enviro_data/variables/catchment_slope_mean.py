from dataclasses import dataclass
@dataclass(frozen=True)
class CatchmentSlopeMeanResult:
    slope_mean_deg: float | None
    status: str
def catchment_slope_mean(values, *, marine=False):
    if marine: return CatchmentSlopeMeanResult(None, "not_applicable_marine")
    vals = [float(v) for v in values if v is not None]
    return CatchmentSlopeMeanResult(sum(vals)/len(vals), "ok") if vals else CatchmentSlopeMeanResult(None, "no_valid_slope_data")
