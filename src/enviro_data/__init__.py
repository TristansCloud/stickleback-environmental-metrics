"""Environmental point enrichment helpers."""

from .climate import ClimateExtractor, ClimateMonth, ClimateResult, RasterProvenance
from .input import (
    CRS,
    InputDiagnostics,
    SiteInputError,
    SiteLoadResult,
    SiteRecord,
    load_sites,
)
from .osm_matching import (
    OSMCandidate,
    OSMMatch,
    OSMMatcher,
    OverpassClient,
    classify_water_feature,
    match_water_feature,
)
from .terrain import CatchmentResult, CatchmentStatus, TerrainExtractor, TerrainSummary
from .pilot import PilotConfig, select_pilot, write_pilot_csv
from .runner import PilotRunResult, run_pilot

__all__ = [
    "CRS",
    "CatchmentResult",
    "CatchmentStatus",
    "ClimateExtractor",
    "ClimateMonth",
    "ClimateResult",
    "InputDiagnostics",
    "OSMCandidate",
    "OSMMatch",
    "OSMMatcher",
    "OverpassClient",
    "RasterProvenance",
    "SiteInputError",
    "SiteLoadResult",
    "SiteRecord",
    "TerrainExtractor",
    "TerrainSummary",
    "classify_water_feature",
    "load_sites",
    "match_water_feature",
    "PilotConfig",
    "select_pilot",
    "write_pilot_csv",
    "PilotRunResult",
    "run_pilot",
]
