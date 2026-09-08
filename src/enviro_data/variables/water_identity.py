"""Identity and controlled class of a matched water feature."""
from ._common import VariableResult

def compute_water_feature_identity(match):
    if match is None or not getattr(match, "osm_id", None):
        return VariableResult(None, "unmatched")
    return VariableResult({"osm_id": match.osm_id, "tags": dict(match.tags), "feature_class": match.feature_class, "match_method": match.match_method}, "ok", {"distance_m": match.distance_m})
