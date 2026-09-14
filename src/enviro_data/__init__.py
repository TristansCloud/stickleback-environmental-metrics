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
from .cached_enrichment import enrich_cached_row, flatten_enriched_row, write_enriched_csv
from .extraction_plan import ExtractionRequest, plan_site, plan_sites
from .habitats import HabitatDomain, normalize_habitat
from .metrics import EnvironmentalMetric, MetricProvenance
from .source_catalog import SOURCES, SourceSpec, SourceVariable, sources_for_habitat
from .temporal import TemporalSummary, summarize_temporal
from .transforms import TransformResult, apply_source_transform

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
    "EnvironmentalMetric",
    "ExtractionRequest",
    "HabitatDomain",
    "MetricProvenance",
    "SOURCES",
    "SourceSpec",
    "SourceVariable",
    "TemporalSummary",
    "TransformResult",
    "apply_source_transform",
    "enrich_cached_row",
    "flatten_enriched_row",
    "normalize_habitat",
    "plan_site",
    "plan_sites",
    "sources_for_habitat",
    "summarize_temporal",
    "write_enriched_csv",
]
