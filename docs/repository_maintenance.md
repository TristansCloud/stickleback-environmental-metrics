# Repository maintenance map

Reviewed 2026-11-01 against `main` at `83d7688` and lake-polygon draft PR #2
at `eb863b2`. Usage below means in-repository callers and tests, not proof
that nobody imports a public helper from a laptop or notebook.

## What to use

| Task | Entry point | State |
| --- | --- | --- |
| Validate the 599-site source | `enviro_data.input.load_sites` | Working; preserve source CSV and stable IDs |
| Select the mixed-habitat 40-site pilot | `enviro_data.pilot.select_pilot` | Working; differs from the lake-only selection |
| Infer site habitat | `scripts/infer_pilot_habitats.py`, `site_habitat.py` | Working helper; inference is not human verification |
| Match nearby OSM features | `scripts/run_pilot_osm.py`, `osm_matching.py` | Existing point-pilot path; not a substitute for whole-lake validation |
| Acquire local terrain and MERIT point values | `scripts/run_staged_pilot.py`, `topography.py`, `hydrology.py` | Working bounded acquisition; catchment delineation still requires a backend |
| Build ecological metrics from frozen rows | `scripts/enrich_cached_pilot.py`, `cached_enrichment.py`, `metrics.py` | Working offline conversion |
| Prepare terrain/MERIT viewer assets | `scripts/prepare_ee_app_assets.py`, `ee_app_assets.py` | Working offline preparation |
| Open the current terrain/MERIT viewer | `apps/earth_engine_validation/ee_pilot_validation_app_current.js` | Registry-based viewer; canonical directory has deployment guidance |
| Retrieve and review whole-lake polygons | PR #2: `run_lake_polygon_pilot.py`, `lake_lookup.py`, `lake_polygons.py`, local OSM scripts | Separate experimental branch; do not merge implicitly during cleanup |

## Keep, retire, or revisit

| Code or artifact | Evidence | Decision |
| --- | --- | --- |
| `input.py`, `pilot.py`, `osm_matching.py`, `dem_acquisition.RasterMetadata`, `topography.extract_window`, `hydrology.py` | Used by acquisition scripts and tests | Keep; these remain foundations despite original commit dates |
| `climate.py` | Exported from the package; tested with fake rasters; no acquisition script calls it | Keep as a local-raster adapter; do not describe climate acquisition as complete |
| `terrain.py` | Exported and tested; staged scripts instead use `topography` and `hydrology` | Retain public API for now; candidate for migration to those modules once callers and CRS/nodata behavior are covered |
| `runner.py` | Exported and tested; no acquisition script calls it | Keep as a selection/plugin scaffold; it does not run the operational pipeline |
| `variables/` | Public re-exports and unit tests; acquisition scripts and cached enrichment do not call it | Keep offline helpers for now; migrate useful calculations to a single provenance contract before deleting wrappers |
| `dem_acquisition.CacheFirstAcquirer`, `AcquisitionConfig`, `topography.extract_point` | Test callers; operational scripts implement their own acquisition/window paths | Revisit consolidation; metadata validation remains actively used and must stay |
| `source_catalog.py`, `extraction_plan.py`, `transforms.py`, `temporal.py`, `habitats.py` | Tested routing/specification layer; habitat normalization also used in cached enrichment | Keep; source specifications/plans are not acquisition adapters |
| `scripts/run_stage_one.py`, `run_online_smoke.py`, `run_merit_earth_engine_smoke.py` | Dated smoke reports and distinct diagnostic scopes | Keep reproducibility entry points; their Copernicus/MERIT code overlaps the staged runner and needs later consolidation |
| Root `apps/ee_pilot_validation_app.js` | Byte-identical to canonical `apps/earth_engine_validation/ee_pilot_validation_app.js`; tests read the canonical file | Removed duplicate; old README now redirects to canonical sources |
| Canonical placeholder template, pinned v3 viewer, current registry viewer | Distinct deployment roles, documented and tested | Keep all three; pinned releases are historical evidence, not accidental duplicates |
| `site_overview_v1_clean.csv`, `pilot_sites_v1.csv`, frozen validation bundles, OSM pilot evidence, derived table | Inputs/provenance or inputs to offline scripts and viewers | Keep; ignored directories can still contain intentionally tracked snapshots |
| Dated reports under `docs/` | Explain earlier runs and limitations | Keep as history; use this map and the README for current navigation |

## Readability changes in this pass

- Expanded compressed statements and calculations in the original variable,
  climate, terrain, and runner modules into conventional multiline Python.
- Made variable exports explicit, retaining the same public helper names.
- Removed unused imports and the exact duplicate viewer.
- Labelled the legacy terrain adapter, plugin scaffold, and polygon-area
  limitation at their definitions.
- Added `requests` to the test extra: a fresh `.[test]` install otherwise fails
  collection because `test_pilot_osm.py` imports a script that requires it.

Calculations, status strings, public call signatures, frozen data, and selected
site IDs are preserved. This pass does not acquire data or publish viewers.

## Follow-up work, in priority order

1. **Resolve the two polygon metric paths before scientific reuse.** The old
   `variables/water_surface_area.py` flattens MultiPolygon rings and subtracts
   every ring after the first as a hole, including other exteriors. The lake
   branch preserves polygon grouping and uses spherical metrics. Do not route
   whole-lake results through the old helper. A replacement needs multipart,
   island, closure, and numerical regression tests plus an explicit choice of
   geometry method and shoreline resolution.
2. **Unify raster semantics before removing the legacy adapter.**
   `TerrainExtractor.summary` samples longitude/latitude without transforming
   into the raster CRS. `ClimateExtractor` has a CRS transformation path;
   topography uses a different finite/nodata policy. Establish one tested
   sampling contract before redirecting public callers. Local-window slope
   and relief are not catchment or shoreline-terrain metrics.
3. **Consolidate acquisition after preserving reproduction behavior.**
   Copernicus URL construction and DEM/MERIT acquisition overlap across smoke,
   one-site, and staged scripts. Cache locations, failure handling, result
   schemas, and runtime counters differ. Move common logic to a package adapter
   with offline fixture coverage, then retain small diagnostic CLI wrappers.
4. **Close scaffolding gaps deliberately.** Neither the terrain placeholder nor
   `hydrology.delineate_catchment` without a supplied backend delineates a
   catchment. The generic runner and most variable wrappers are disconnected
   from operational scripts. Either wire them to the current metric/provenance
   model or deprecate them with a documented replacement; do not remove only
   their tests and call that evidence of non-use.
5. **Clarify runtime and cache selection.** Packaging advertises Python 3.10,
   but several scripts import Python 3.11's `tomllib` directly.
   `latest_cached_pilot()` selects by directory name, not a release manifest.
   Choose and test a supported runtime and an explicit release-selection rule
   before changing either behavior.

## Validation

The baseline main suite passed 56 tests after installing its actual dependencies.
Changes are checked against the same offline suite and a syntax-tree comparison
of the formatting-only modules. No live OSM, Earth Engine, or DEM run is needed
for this maintenance pass. The lake branch is inspected separately, without
changing its head or including it in this cleanup branch.
