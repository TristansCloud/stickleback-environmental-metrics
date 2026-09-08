"""Shoreline development index (perimeter divided by equal-area circle perimeter)."""
import math
from ._common import VariableResult
from .water_perimeter import compute_water_perimeter
from .water_surface_area import compute_water_surface_area

def compute_shoreline_development(candidate):
    area, perimeter = compute_water_surface_area(candidate), compute_water_perimeter(candidate)
    if area.status != "ok" or perimeter.status != "ok": return VariableResult(None, "unavailable", {"reason": "area_and_perimeter_required"})
    if not area.value: return VariableResult(None, "undefined", {"reason": "zero_area"})
    return VariableResult(perimeter.value / (2 * math.sqrt(math.pi * area.value)), "ok", {"dimensionless": True})
