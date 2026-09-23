# Stickleback environmental data pipeline

This repository contains the first implementation layer for enriching global water-sample coordinates. The checked-in `site_overview_v1_clean.csv` is an immutable source artifact. It contains 599 validated WGS84 (`EPSG:4326`) records with stable `sample_id` values.

## Quick start

### Lake polygon pilot

The pilot deterministically selects a geographically spread subset of 40
distinct, name-inferred freshwater lake sites from the checked-in 599-site
input. The selection is a working classification, not field confirmation.
`data/lake_pilot/run_metadata.json` records the selected IDs for each local run.
The lake pipeline uses OSM ID/tag discovery within
100 m, then 500 m, and requests complete geometry for at most three ranked
lake candidates at each distance. It accepts lake geometry only if it is
closed, complete, and contains the sample coordinate. Holes (islands) reduce
area and contribute to the reported shoreline length. It also records OSM
name evidence. All candidate geometries require human identity review.

```text
python scripts/run_lake_polygon_pilot.py
python scripts/run_lake_polygon_pilot.py --live-osm
```

The first command inspects only local cached OSM responses. The live option
sends site coordinates to public Overpass. It waits at least 2 seconds between
calls, caps each call at 10 seconds/8 MB, makes no automatic retry, and stops
after two consecutive failed sites. Results and caches remain local under
`data/lake_pilot/`. The CSV tracks area (m²), total shoreline including
islands (m), area/perimeter (m), and dimensionless shoreline development.
GeoJSON stores the corresponding whole candidate polygons. A candidate is
not a confirmed waterbody. Nothing computes lake depth yet; that requires
the precise equation from the user's thesis and a defined shoreline terrain
sampling policy. Climate sources are catalogued but not collected by this run.

```python
from enviro_data.input import load_sites

result = load_sites("site_overview_v1_clean.csv")
if result.diagnostics.has_errors:
    raise ValueError(result.diagnostics.format())
for site in result.records:
    print(site.sample_id, site.latitude, site.longitude)
```

Coordinates are parsed as WGS84 (`EPSG:4326`) decimal degrees. The input module performs schema, required-value, numeric, range, duplicate-ID, and row-level validation.

Current modules:

- `enviro_data.input`: immutable input loading and validation.
- `enviro_data.osm_matching`: cached, optional OSM/Overpass retrieval and deterministic water-feature matching. Tests use offline fixtures rather than live queries.
- `enviro_data.climate`: local-raster monthly tmin, tmax, and precipitation sampling with per-raster provenance.
- `enviro_data.terrain`: local DEM sampling that preserves nodata and an explicit future catchment-delineation interface.
- `enviro_data.dem_acquisition`: bounded, cache-first DEM/hydrology source handling and provenance for the pilot.
- `enviro_data.topography`: local topographic extraction from cached raster windows.
- `enviro_data.hydrology`: hydrologic/catchment status and MERIT Hydro integration boundary.
- `enviro_data.habitats`: canonical freshwater, transition, and marine routing.
- `enviro_data.metrics`: one status/provenance contract for analysis-ready variables.
- `enviro_data.cached_enrichment`: converts the frozen pilot cache into ecological metrics without network access.
- `enviro_data.source_catalog`: versioned active and candidate global data sources.
- `enviro_data.extraction_plan`: serializable, habitat-aware requests for future bounded acquisition.
- `enviro_data.transforms`: checked unit/scale transforms declared by the source catalog.
- `enviro_data.temporal`: mean, extremes, range, variability, and missingness summaries.

### Reuse the completed pilot

The checked-in validation bundle already contains Copernicus terrain and
MERIT Hydro point values. Convert the latest frozen bundle to a wide,
analysis-ready table with:

```text
python scripts/enrich_cached_pilot.py
```

The default output is
`data/derived/pilot_ecological_metrics_v1.csv`. Every environmental value has
companion status, unit, ecological-axis, source, version, method, and spatial-
scale columns. Marine-inapplicable values and source no-data remain null; they
are never written as zero.

The source catalog currently routes JRC Global Surface Water and ERA5-Land to
freshwater/transition sites; OISST, HYCOM, and MODIS ocean colour to
marine/transition sites; and ESA WorldCover to terrestrial buffers or
catchments for all known habitats. These entries are verified source
specifications, not permission for an unbounded run. See
`docs/environmental_variable_roadmap.md` for the ecological interpretation and
remaining implementation gates.

For the first pass, the 40-site pilot uses Copernicus DEM GLO-30 (accepted as
DSM topography) and MERIT Hydro (accepted for hydrologic context). The source
selection is provisional: a later pilot-only comparison will exchange data
sources and compare outputs using the recorded provenance. The configuration
keeps network access disabled by default and caps the scope at 40 sites.

The repository does not yet ship DEM/climate rasters or execute a production-scale OSM/catchment run. Those inputs and source/version configuration remain the next integration step.

### Earth Engine validation viewer

The reusable, read-only validation-App source and its deployment guidance are
in [apps/earth_engine_validation](apps/earth_engine_validation/README.md).
It prepares frozen, versioned pilot evidence locally and uses a stable registry
asset to select one approved immutable release. Generated review bundles remain
local and are intentionally excluded from Git.

### Earth Engine pilot configuration

The checked-in [config/earth_engine.toml.example](config/earth_engine.toml.example)
contains the bounded MERIT Hydro settings for the deterministic 40-site pilot.
Copy it to `config/earth_engine.toml` and set the registered Google Cloud
project ID (the local copy is ignored). The current local project is
`stickleback-507923`.

Earth Engine authentication is performed separately through the local Earth
Engine Python/CLI credential store. Do not place OAuth tokens, service-account
keys, passwords, or other secrets in either TOML file. The configuration does
not authorize a full MERIT download; it is for bounded pilot requests only.

Install and run offline checks with:

```text
python -m pip install -e ".[test]"
python -m pytest
```

Install optional integrations only when required:

```text
python -m pip install -e ".[terrain,earth-engine,osm]"
```
