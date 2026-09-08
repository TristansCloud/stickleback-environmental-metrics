from dataclasses import dataclass
@dataclass(frozen=True)
class MonthlyPrecipitationResult:
    precipitation_mm: float | None
    status: str
def monthly_precipitation(value_mm, *, marine=False):
    if marine: return MonthlyPrecipitationResult(None, "not_applicable_marine")
    if value_mm is None: return MonthlyPrecipitationResult(None, "no_valid_data")
    if value_mm < 0: return MonthlyPrecipitationResult(None, "invalid_value")
    return MonthlyPrecipitationResult(float(value_mm), "ok")
