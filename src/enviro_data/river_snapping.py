"""Bounded, provisional stream-vector and MERIT-cell matching.

Vector distances use a local tangent plane centred on the input point. This is
an approximate pilot matcher, not catchment delineation or flow-path validation.
"""

from __future__ import annotations

import math
from typing import Mapping

from .site_habitat import normalize_site_name

BANDS = ("elv", "dir", "upa", "upg", "wth", "wat")
METRICS = {
    "upa": ("upstream_drainage_area_km2", "km2"),
    "upg": ("upstream_drainage_pixels", "count"),
    "wth": ("channel_width_m", "m"),
}
RADIUS = 6371008.8


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def point(lon, lat):
    lon, lat = number(lon), number(lat)
    if lon is None or lat is None or not -180 <= lon <= 180 or not -89 <= lat <= 89:
        raise ValueError("invalid or polar WGS84 coordinate")
    return lon, lat


def xy(coordinate, origin):
    lon, lat = point(*coordinate)
    origin_lon, origin_lat = origin
    delta = (lon - origin_lon + 180) % 360 - 180
    return (
        RADIUS * math.radians(delta) * math.cos(math.radians(origin_lat)),
        RADIUS * math.radians(lat - origin_lat),
    )


def distance(a, b):
    return math.hypot(*xy(a, b))


def nearest_on_geometry(origin, geometry):
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    parts = (
        [coordinates]
        if kind == "LineString"
        else coordinates if kind == "MultiLineString" else []
    )
    best = None
    for part in parts:
        for a, b in zip(part, part[1:]):
            ax, ay = xy(a[:2], origin)
            bx, by = xy(b[:2], origin)
            dx, dy = bx - ax, by - ay
            length2 = dx * dx + dy * dy
            if length2 == 0:
                continue
            fraction = max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
            x, y = ax + fraction * dx, ay + fraction * dy
            gap = math.hypot(x, y)
            lon = (
                origin[0]
                + math.degrees(x / (RADIUS * math.cos(math.radians(origin[1]))))
                + 180
            ) % 360 - 180
            lat = origin[1] + math.degrees(y / RADIUS)
            if best is None or gap < best["distance_m"]:
                best = {"longitude": lon, "latitude": lat, "distance_m": gap}
    return best


def name_evidence(site_name, properties):
    generic = {"river", "stream", "creek", "brook", "lower", "upper", "mid", "marine"}
    site = set(normalize_site_name(site_name).split()) - generic
    names = [
        properties.get(k) for k in ("name", "name:en", "alt_name") if properties.get(k)
    ]
    if not site or not names:
        return "unavailable"
    for name in names:
        tokens = set(normalize_site_name(name).split()) - generic
        if tokens and (site <= tokens or tokens <= site):
            return "agrees"
    return "differs"


def snap_stream(row: Mapping, features, *, max_distance_m=500.0, ambiguity_m=25.0):
    if not 0 < max_distance_m <= 500 or not 0 <= ambiguity_m <= max_distance_m:
        raise ValueError(
            "snap bounds must satisfy 0 <= ambiguity <= max_distance <= 500"
        )
    origin = point(row["Longitude"], row["Latitude"])
    candidates, rejected, used = [], [], set()
    for feature in features:
        props = feature.get("properties") or {}
        reach_id = str(
            feature.get("id") or props.get("HYRIV_ID") or props.get("osm_id") or ""
        )
        if not reach_id or reach_id in used:
            rejected.append(
                {"reach_id": reach_id, "reason": "missing_or_duplicate_identity"}
            )
            continue
        used.add(reach_id)
        # HydroRIVERS IDs identify network reaches; OSM must identify a channel.
        if not props.get("HYRIV_ID") and props.get("waterway") not in {
            "river",
            "stream",
        }:
            continue
        try:
            snapped = nearest_on_geometry(origin, feature.get("geometry") or {})
        except (ValueError, TypeError, IndexError):
            rejected.append({"reach_id": reach_id, "reason": "invalid_geometry"})
            continue
        if snapped is None or snapped["distance_m"] > max_distance_m:
            continue
        candidates.append(
            {
                **snapped,
                "reach_id": reach_id,
                "name": props.get("name"),
                "name_evidence": name_evidence(row["Population.name"], props),
                "properties": props,
                "geometry": feature["geometry"],
            }
        )
    candidates.sort(key=lambda c: (c["distance_m"], c["reach_id"]))
    result = {
        "status": "no_candidate",
        "original_longitude": origin[0],
        "original_latitude": origin[1],
        "candidate_count": len(candidates),
        "candidates": candidates,
        "rejected": rejected,
        "selected": None,
        "review_required": True,
        "flow_connection_verified": False,
    }
    if not candidates:
        return result
    best = candidates[0]
    if row.get("validation_role") == "challenge" or row["Ecotype"] != "freshwater":
        result["status"] = "classification_review_required"
    elif (
        len(candidates) > 1
        and candidates[1]["distance_m"] - best["distance_m"] <= ambiguity_m
    ):
        result["status"] = "ambiguous_reaches"
    elif best["name_evidence"] == "differs":
        result["status"] = "name_conflict"
    else:
        result.update(status="provisional_vector_match", selected=best)
    return result


def align_merit_cell(snap, cells, *, radius_m=150.0, corridor_m=90.0, min_area_km2=1.0):
    """Require modelled channel support; do not choose maximum accumulation.

    Positive width deliberately excludes unsupported narrow/masked channels.
    It is not evidence that the model cell belongs to the named river.
    """
    if not 0 < radius_m <= 500 or not 0 < corridor_m <= 150 or min_area_km2 <= 0:
        raise ValueError("invalid raster alignment bounds")
    selected = snap.get("selected")
    if selected is None:
        return {"status": "vector_unresolved", "selected": None, "candidates": []}
    origin = (selected["longitude"], selected["latitude"])
    candidates = []
    for cell in cells:
        lon, lat = point(cell["longitude"], cell["latitude"])
        values = {band: number(cell.get("values", {}).get(band)) for band in BANDS}
        gap = distance((lon, lat), origin)
        on_line = nearest_on_geometry((lon, lat), selected["geometry"])
        if (
            gap <= radius_m
            and on_line
            and on_line["distance_m"] <= corridor_m
            and values["upa"] is not None
            and values["upa"] >= min_area_km2
            and values["wth"] is not None
            and values["wth"] > 0
            and values["dir"] in {0, 1, 2, 4, 8, 16, 32, 64, 128}
        ):
            candidates.append(
                {
                    **cell,
                    "values": values,
                    "distance_from_vector_snap_m": gap,
                    "distance_from_vector_m": on_line["distance_m"],
                }
            )
    candidates.sort(
        key=lambda c: (c["distance_from_vector_snap_m"], c["longitude"], c["latitude"])
    )
    result = {
        "status": "no_supported_channel_cell",
        "selected": None,
        "candidates": candidates,
    }
    if not candidates:
        return result
    best = candidates[0]
    # Large accumulation changes among almost equally near cells may signal a
    # confluence or parallel main channel. Keep them for review, not as a maximum.
    if any(
        c["distance_from_vector_snap_m"] <= best["distance_from_vector_snap_m"] + 50
        and max(c["values"]["upa"], best["values"]["upa"])
        / min(c["values"]["upa"], best["values"]["upa"])
        > 2
        for c in candidates[1:]
    ):
        result["status"] = "ambiguous_channel_cells"
    else:
        result.update(status="provisional_channel_cell", selected=best)
    return result


def comparison_metrics(raw, alignment):
    """Preserve missingness and distinguish raw point from provisional channel."""
    selected = alignment.get("selected")
    after = selected["values"] if selected else {}
    output = {}
    for band, (name, unit) in METRICS.items():
        before = number(raw.get(band))
        value = number(after.get(band))
        if before is not None and before < 0:
            before = None
        if value is not None and value < 0:
            value = None
        output[name] = {
            "unit": unit,
            "original": before,
            "channel": value,
            "delta": (
                value - before if value is not None and before is not None else None
            ),
            "original_status": "ok" if before is not None else "no_valid_data",
            "channel_status": (
                "provisional" if value is not None else alignment["status"]
            ),
        }
    return output
