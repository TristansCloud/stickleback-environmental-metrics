# Full environmental review workflow

This workflow produces a reviewable row for every one of the 599 original
samples, with provisional classes and available environmental context. The
immutable input and reviewed labels are separate. Marine-specific variables,
shoreline slope, and lake depth remain empty.

## Reproduce

Install Python 3.11+ and the integrations used here:

```sh
python -m pip install -e ".[test,local-osm]"
```

Start small, then expand successful paths. All network flags default off.
Point queries are resumable, cached, and checked against original coordinates.

```sh
# Point pilot, then full coverage (NASA POWER and point DEM were reliable).
python scripts/collect_point_review_data.py --max-sites 26 --live
python scripts/collect_point_review_data.py --max-sites 599 --live

# Recover previously identified lake objects directly, without Overpass discovery.
python scripts/collect_lake_review.py --limit 5 --max-requests 5 --live
python scripts/collect_lake_review.py --limit 24 --max-requests 24 --live

# Download official regional stream networks and match locally.
python scripts/prepare_hydrorivers_vectors.py --regions eu na --live
python scripts/run_river_pilot.py --vectors data/cache/hydrorivers/nearby_reaches.geojson

# Local global lake fallback: approximately 820 MB compressed, several GB extracted.
python scripts/prepare_hydrolakes_review.py --live
```

The original `--discover` lake path is optional and bounded at a 500 m nearby
query. It is not required to use the local HydroLAKES fallback. Do not repeat
failing Overpass discovery for the full dataset: the latest river discovery
trial stopped after repeated timeouts. Previously known core OSM objects worked.

The `build_full_review.py` defaults use the combined lake directory, full local
river results, and local shoreline profiles prepared by the orchestration
command below. Use the end-to-end script to reproduce those intermediate
selections and merges:

```sh
python -m scripts.generate_full_review --live
```

It uses the checked-in stream/lake cohort definitions for pilot checks and
requires no new labels from Marius. Missing scientific measurements stay null.
A CSV with fewer available lake/river measurements is still a complete **site
review table**, not a scientifically complete environmental dataset.

## What each family means

| Family | Source and interpretation | Limits |
| --- | --- | --- |
| Point elevation | Open-Meteo's Copernicus GLO-90 2021 DEM service, metres | DSM at original point; not bathymetry or measured water surface; marine zero is not ocean depth |
| Climate | NASA POWER/MERRA-2 monthly and annual atmospheric climatology | Source-returned period January 2001–December 2025; air temperature, not water temperature; precipitation is **mm/day**, not annual mm |
| Climate sharing | Nearest nominal MERRA-2 0.5° latitude × 0.625° longitude cell; one representative per cell | Many sites intentionally share regional context; original coordinates are unchanged; source query and representative metadata are retained |
| Frozen point pilot | Existing 40-site Copernicus/MERIT table | `cached_point_*` values are historical original-point samples, not snapped channel/catchment measurements |
| Lake geometry | Previously known OSM objects plus HydroLAKES v1.0 point-containment candidates | Original point must be covered; no forced snap; HydroLAKES omits lakes below 10 ha; unnamed/ambiguous cases still need identity review |
| Lake shape metrics | Whole polygons, spherical area and great-circle segment perimeter; island holes subtracted from area and included in shoreline | Raw source geometry resolution; shoreline normalization is still pending and cross-source perimeter differences are not ecological effects |
| River reach attributes | Local HydroRIVERS v1.0; nearest unambiguous candidate within 500 m | Upstream area refers to **reach outlet**, not exact sample point; discharge is estimated long-term mean; name identity and flow connection remain unverified |
| River MERIT alignment | Optional local rasters or Earth Engine native-grid sampling | Separate from vector snap; requires a supported nearby cell, positive width, valid flow direction, upstream area ≥1 km², and no strong competing-cell accumulation jump |
| Shoreline relative elevation | Cached Copernicus GLO-90 native raster cells; median water-interior DEM proxy versus external distance bands | Exploratory DSM proxy; includes vegetation/buildings; no depth equation; surface proxy must be sufficiently sampled and stable |

Climate grouping was checked against individually retrieved pilot values:
values agreed within shared nominal cells, and a direct nominal-cell-center
probe agreed with the original point's climatology. Retain that nominal-grid
assumption and all returned metadata; it is not a fine-scale climate estimate.
The provider currently exposes a precomputed climatology period. The attempted
custom-period endpoint returned 404, so this workflow records the actual
source-returned baseline instead of labelling it as 2001–2020.

The review table includes both `lake_area_perimeter_m = A/P` and the distinct,
dimensionless `lake_shoreline_development = P/(2*sqrt(pi*A))`.

## Shoreline exploration

Lake-interior sample points are selected from a 90 m inset where possible.
A deterministic grid provides up to 12 interior and 20 terrain samples per
external band: **0–50 m, 50–100 m, and 100–250 m** from water boundaries,
including island shores. These are disjoint bands, not the thesis's unknown
variable-buffer rule. The 50 m band is below nominal DEM resolution and is
labelled accordingly; sample points are not independent raster cells.

A water-surface proxy is withheld from relative calculations if the inset is
unavailable, too few valid interior samples exist, or their elevation range
exceeds 5 m. This threshold is a provisional QA heuristic, not a calibrated
scientific criterion. Large lakes beyond the local projection's 200 km extent
are explicitly unsupported. Invalid geometry, missing tiles, and unstable
surface proxies are never replaced by depth estimates or zero elevations.

The next scientific input remains the thesis equation, buffer selection rule,
and definition of lake surface elevation. Existing DSM-derived relative terrain
values can support that work, but must not be presented as measured lake depth.

## River matching and missing MERIT

The seven-site stream pilot includes two deliberate classification challenges;
they are retained for inspection without assigning definitive channel metrics.
The expanded inferred-stream cohort contains 61 sites. `--max-sites 61` explicitly
raises the default seven-site bound; the CLI caps expansion at 100 sites.
GeoJSON keeps original points, candidate reaches, selected vector points, and
MERIT cell centres when available. Distances are local tangent-plane estimates;
competing reaches within 25 m of the nearest distance are unresolved.

HydroRIVERS area, order and discharge are distinct source reach attributes.
`river_snapped_*` fields remain empty until MERIT raster alignment succeeds.
Earth Engine credentials/configuration and local MERIT rasters are absent in
this environment. No authentication or full MERIT global download was attempted.
A laptop with configured Earth Engine can use:

```sh
python -m pip install -e ".[earth-engine,local-osm]"
python scripts/run_river_pilot.py --vectors data/cache/hydrorivers/nearby_reaches.geojson --live-merit --ee-config config/earth_engine.toml --output-dir data/cache/river_merit_laptop
```

Alternatively pass `--merit-rasters paths.json`, with native, aligned WGS84
3-arc-second rasters for `elv`, `dir`, `upa`, `upg`, `wth`, and `wat`:

```json
{"dataset":"MERIT/Hydro/v1_0_1","bands":{"elv":"elv.tif","dir":"dir.tif","upa":"upa.tif","upg":"upg.tif","wth":"wth.tif","wat":"wat.tif"}}
```

Paths are relative to the JSON file. Width missing for a narrow stream means
alignment is unsupported; it is not permission to choose the largest nearby river.

## Storage, review, and source attribution

All downloaded archives, Shapefiles, GeoTIFF tiles, derived GeoJSON, raw API
responses and generated review outputs live under ignored `data/cache/`.
They are **not committed to Git**. Scripts, tests and documentation are committed.
GeoTIFF (`.tif`) holds rasters; GeoJSON holds small review vector subsets;
Shapefile is a group of `.shp`, `.shx`, `.dbf`, and `.prj` files, usually zipped.
A home server can retain these geofiles durably; a GeoPackage (`.gpkg`) is useful
for consolidating large vector layers later. The current environment has enough
space for the regional/local subset, but not the approximately 195 GB global
MERIT package. Raw cache files are reproducible and transient here.

Share the generated review CSV and its README/provenance with Marius. He can
fill `reviewed_waterbody_class`, waterbody name, corrected coordinates, reviewer,
and notes by stable sample ID. Never overwrite the original class or coordinate
evidence, and do not mistake lexical inference confidence for confirmed habitat.

Primary source documentation:

- [HydroRIVERS](https://www.hydrosheds.org/products/hydrorivers), Lehner & Grill (2013).
- [HydroLAKES](https://www.hydrosheds.org/products/hydrolakes), Messager et al. (2016), CC BY 4.0.
- [MERIT Hydro](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1), Yamazaki et al. (2019).
- [NASA POWER point-request guidance](https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/) and [climatology](https://power.larc.nasa.gov/docs/services/api/temporal/climatology/).
- [Copernicus DEM on AWS](https://registry.opendata.aws/copernicus-dem/) and [Open-Meteo elevation](https://open-meteo.com/en/docs/elevation-api).
- OSM geometries: © OpenStreetMap contributors, ODbL; retain attribution and source provenance when sharing derived results.
