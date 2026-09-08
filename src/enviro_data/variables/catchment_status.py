from dataclasses import dataclass

@dataclass(frozen=True)
class CatchmentStatusResult:
    status: str
    message: str = ""

def catchment_status(*, geometry=None, delineation_attempted=False, marine=False):
    if marine: return CatchmentStatusResult("not_applicable_marine")
    if geometry is not None: return CatchmentStatusResult("available")
    if delineation_attempted: return CatchmentStatusResult("unavailable")
    return CatchmentStatusResult("not_requested")
