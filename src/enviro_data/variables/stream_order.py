"""Stream order; deliberately unavailable without supplied network topology."""
from ._common import VariableResult, tags_of

def compute_stream_order(candidate=None, topology=None, **kwargs):
    if topology is None: return VariableResult(None, "unavailable", {"reason": "network_topology_required"})
    osm_id = getattr(candidate, "osm_id", candidate if isinstance(candidate, str) else None)
    order = topology.get(osm_id) if hasattr(topology, "get") else None
    return VariableResult(order, "ok" if order is not None else "unavailable", {} if order is not None else {"reason": "feature_not_in_topology"})
