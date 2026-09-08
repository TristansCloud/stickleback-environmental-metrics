from dataclasses import dataclass
@dataclass(frozen=True)
class UnpavedRoadResult:
    length_km: float | None
    density_km_per_km2: float | None
    status: str
def unpaved_road_length_density(segments, *, area_km2=None):
    length = sum(float(s.get("length_m", 0)) for s in segments if s.get("surface", "").lower() in {"unpaved", "gravel", "dirt", "ground"}) / 1000
    density = length / float(area_km2) if area_km2 and area_km2 > 0 else None
    return UnpavedRoadResult(length, density, "ok" if density is not None else "ok_length_only")
