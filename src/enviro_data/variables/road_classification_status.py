from dataclasses import dataclass
@dataclass(frozen=True)
class RoadClassificationStatusResult:
    status: str
    classified_count: int = 0
    total_count: int = 0
def road_classification_status(segments):
    total = len(segments)
    classified = sum(1 for s in segments if s.get("class") or s.get("highway"))
    if total == 0: return RoadClassificationStatusResult("no_roads", 0, 0)
    return RoadClassificationStatusResult("ok" if classified == total else "partial", classified, total)
