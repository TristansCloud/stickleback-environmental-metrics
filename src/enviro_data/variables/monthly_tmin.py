from dataclasses import dataclass
@dataclass(frozen=True)
class MonthlyTminResult:
    tmin_c: float | None
    status: str
def monthly_tmin(value_c, *, marine=False):
    if marine: return MonthlyTminResult(None, "not_applicable_marine")
    return MonthlyTminResult(None, "no_valid_data") if value_c is None else MonthlyTminResult(float(value_c), "ok")
