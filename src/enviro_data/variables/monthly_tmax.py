from dataclasses import dataclass
@dataclass(frozen=True)
class MonthlyTmaxResult:
    tmax_c: float | None
    status: str
def monthly_tmax(value_c, *, marine=False):
    if marine: return MonthlyTmaxResult(None, "not_applicable_marine")
    return MonthlyTmaxResult(None, "no_valid_data") if value_c is None else MonthlyTmaxResult(float(value_c), "ok")
