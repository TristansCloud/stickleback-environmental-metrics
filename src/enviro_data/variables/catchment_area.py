from dataclasses import dataclass
@dataclass(frozen=True)
class CatchmentAreaResult:
    area_km2: float | None
    status: str
def catchment_area(area_km2, *, marine=False):
    if marine: return CatchmentAreaResult(None, "not_applicable_marine")
    if area_km2 is None: return CatchmentAreaResult(None, "no_catchment")
    if area_km2 < 0: return CatchmentAreaResult(None, "invalid_area")
    return CatchmentAreaResult(float(area_km2), "ok")
