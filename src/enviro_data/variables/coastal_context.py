"""Coastal proximity context derived from distance-to-coast."""
from ._common import VariableResult
from .distance_to_coast import compute_distance_to_coast

def compute_coastal_context(point, coast_candidates, threshold_m=1000.0):
    distance = compute_distance_to_coast(point, coast_candidates)
    if distance.status != "ok": return VariableResult(None, "unavailable", dict(distance.diagnostics))
    return VariableResult({"distance_to_coast_m": distance.value, "within_threshold": distance.value <= threshold_m, "threshold_m": threshold_m}, "ok", distance.diagnostics)
