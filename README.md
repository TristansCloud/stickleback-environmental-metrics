# Environmental data pipeline (v1)

This repository contains the first implementation layer for enriching global water-sample coordinates. The checked-in `site_overview_v1_clean.csv` is an immutable source artifact. It contains 599 validated WGS84 (`EPSG:4326`) records with stable `sample_id` values.

## Quick start

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

For the first pass, the 40-site pilot uses Copernicus DEM GLO-30 (accepted as
DSM topography) and MERIT Hydro (accepted for hydrologic context). The source
selection is provisional: a later pilot-only comparison will exchange data
sources and compare outputs using the recorded provenance. The configuration
keeps network access disabled by default and caps the scope at 40 sites.

The repository does not yet ship DEM/climate rasters or execute a production-scale OSM/catchment run. Those inputs and source/version configuration remain the next integration step.

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

Run checks with:

```text
python -m pytest
```
