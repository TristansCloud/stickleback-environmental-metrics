from dataclasses import dataclass
@dataclass(frozen=True)
class MonthlyCatchmentPrecipitationVolumeResult:
    volume_m3: float | None
    status: str
def monthly_catchment_precipitation_volume(precipitation_mm, area_km2, *, marine=False):
    if marine: return MonthlyCatchmentPrecipitationVolumeResult(None, "not_applicable_marine")
    if precipitation_mm is None or area_km2 is None: return MonthlyCatchmentPrecipitationVolumeResult(None, "insufficient_data")
    if precipitation_mm < 0 or area_km2 < 0: return MonthlyCatchmentPrecipitationVolumeResult(None, "invalid_value")
    return MonthlyCatchmentPrecipitationVolumeResult(float(precipitation_mm) * float(area_km2) * 1000.0, "ok")
