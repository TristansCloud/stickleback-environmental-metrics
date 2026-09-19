# Environmental-variable expansion roadmap

## Design rule

The pipeline treats freshwater, marine–freshwater transition, and marine
populations as positions on ecological gradients. Source routing is explicit,
but transition sites deliberately receive both terrestrial/hydrologic and
marine candidates. Every value must retain its source, version, method,
spatial scale, unit, status, and relevant temporal window.

The source specifications below were checked against the official Earth Engine
catalog on 2026-09-14. Catalog presence does not imply that a coarse product is
valid at a narrow estuary, fjord, stream, or shoreline point. Spatial support
and masked-cell behavior must be validated in the 40-site pilot before the
599-site run.

## Implemented from the frozen pilot

`scripts/enrich_cached_pilot.py` reuses the stored MERIT Hydro and Copernicus
values without new retrieval. It emits:

| Output | Ecological interpretation | Important limitation |
| --- | --- | --- |
| `local_terrain_elevation_m` | broad topographic setting | terrain beside water is not water-surface elevation |
| `local_terrain_slope_deg` | local terrain energy/topographic confinement | not channel gradient |
| `local_terrain_relief_m` | local structural relief | calculated from a 3×3 GLO-30 window |
| `upstream_drainage_area_km2` | catchment size/freshwater influence | point value requires drainage snapping checks |
| `log10_upstream_drainage_area` | analysis-friendly catchment-size transform | derived as `log10(1 + area_km2)` |
| `height_above_drainage_m` | floodplain/drainage position | MERIT model value, not surveyed height |
| `channel_width_m` | habitat size and flow context | present at only 3 of 40 pilot points |
| `flow_direction_d8` | routing diagnostic | categorical code, not an evolutionary predictor by itself |
| `water_body_mask` | point-placement diagnostic | categorical source value |

The output also carries a local terrain gradient calculated from terrain slope.
It is labelled explicitly as **not channel gradient** and should not be used as
a stream-power term.

## Verified next-source catalog

| Source | Candidate variables | Routed habitats | Scale/caution |
| --- | --- | --- | --- |
| [JRC Global Surface Water v1.4](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater) | occurrence, seasonality, recurrence | freshwater, transition | 30 m; narrow channels and shoreline registration need review |
| [ERA5-Land monthly](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR) | air/lake temperature, precipitation, runoff | freshwater, transition | ~11 km; climate exposure, not fine-scale water measurements |
| [NOAA OISST v2.1](https://developers.google.com/earth-engine/datasets/catalog/NOAA_CDR_OISST_V2_1) | SST mean/range/extremes, anomaly, sea ice | marine, transition | ~28 km; generally too coarse inside small estuaries |
| [HYCOM temperature/salinity](https://developers.google.com/earth-engine/datasets/catalog/HYCOM_sea_temp_salinity) | surface temperature and salinity | marine, transition | ~8.9 km; apply documented scale and offset |
| [HYCOM velocity](https://developers.google.com/earth-engine/datasets/catalog/HYCOM_sea_water_velocity) | current components and derived speed | marine, transition | ~8.9 km; historical series currently ends in 2024 |
| [MODIS Aqua ocean colour](https://developers.google.com/earth-engine/datasets/catalog/NASA_OCEANDATA_MODIS-Aqua_L3SMI) | chlorophyll-a, particulate organic carbon, light attenuation, available radiation | marine, transition | ~4.6 km; coastal optical bias and cloud/ice missingness |
| [ESA WorldCover v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) | terrestrial land-cover fractions | all habitats | 10 m; summarize land-only catchments/buffers, never the water point alone |

`enviro_data.source_catalog` stores the exact asset IDs, bands, units,
transform requirements, routing, spatial scale, and documentation link.
`enviro_data.extraction_plan` turns validated sites into serializable requests,
but does not perform network access.
`enviro_data.transforms` applies the catalogued scale, offset, and unit rules,
and `enviro_data.temporal` retains mean, extrema, range, standard deviation,
coefficient of variation, and missing-value counts for retrieved series.

## Recommended implementation sequence

1. Validate JRC water occurrence/seasonality and ERA5-Land monthly summaries on
   the 40 sites. Compute long-term mean, seasonal amplitude, relevant extreme,
   and interannual variation rather than only a grand mean.
2. Snap freshwater coordinates to a hydrologic network, retain snap distance,
   and validate MERIT upstream area against known lake/river identity.
3. Add catchment delineation and network-derived stream order, distance to the
   sea, accessible network length, and downstream barriers. Do not infer stream
   order from upstream area alone.
4. Validate OISST/HYCOM/MODIS water-only neighborhoods for marine sites. Compare
   point, nearest-valid-water, and 3×3-water-window policies.
5. Treat transition sites as a separate validation problem. Combine upstream
   drainage, distance through water to the mouth, tidal information, and marine
   salinity; do not label coarse HYCOM salinity as measured estuarine salinity.
6. Add land-cover fractions over validated catchments or coastal terrestrial
   buffers. Preserve geometry and denominator definitions.

## Remaining sources and scientific decisions

- A global river network with authoritative stream order and along-network
  distance, such as HydroRIVERS/RiverATLAS, is still needed.
- Bathymetry, wave exposure, tides, and estuary geometry need source selection.
- Calcium, alkalinity, pH, dissolved oxygen, predators, prey, parasites, and
  submerged vegetation require either weaker GIS proxies or field validation.
- The current `marine-freshwater` label does not distinguish estuary, lagoon,
  anadromous collection, or freshwater site with marine ancestry. A separate
  habitat classification table should be created before estuary-specific
  inference.
- Temporal windows should be aligned to collection/breeding dates when those
  dates are available; otherwise the climatology period must be explicit.

## Full-run gate

Do not expand automatically to 599 sites until the 40-site review has checked:

- habitat routing and point placement;
- spatial support and nearest-valid-water behavior;
- transformations, units, masks, and genuine zeros;
- missingness by habitat and geography;
- a small set of known locations against field knowledge;
- collinearity and redundancy among derived predictors;
- immutable cache and provenance completeness.
