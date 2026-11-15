# Current project status

Documentation review: 2026-11-14, against `main` at `2c6d8c3`.
This page separates implemented methods, previously recorded run coverage and
remaining validation. This documentation pass did not rerun collection, inspect
cloud assets or verify the currently published App.

## What is implemented

| Family | Current path | Interpretation |
| --- | --- | --- |
| Source and climate | 599 original sites; cached point elevation and NASA POWER climatology | Original IDs/coordinates/ecotypes retained; atmospheric context, not water temperature |
| Lake geometry | `scripts/closest_water_599.py`; selected OSM lake polygons, including near-shore proposals | Candidate identities; containing and near-shore matches must remain distinguishable |
| Lake shape | `enviro_data.lake_polygons.polygon_metrics` | Water area excludes islands; perimeter includes island shores; raw source geometry |
| Drainage area | `scripts/collect_merit_maxima.py` | Native-grid MERIT `upa` maximum within a lake polygon or a 150 m stream buffer |
| Shoreline terrain | `scripts/collect_full_band_shoreline.py`, `enviro_data.shoreline_full_band` | Every valid native GLO-90 cell centre in disjoint exterior bands; islands included |
| Viewer | `apps/earth_engine_validation/ee_full_review_app.js` | Supports separate lookup and MERIT/site-metrics assets layered onto the original review release |

The original `scripts/generate_full_review.py` orchestration reproduces the
November 1 workflow, including HydroLAKES fallback and earlier point-sampled
shoreline profiles. It does **not** orchestrate all of the later OSM, MERIT-maxima
and whole-band refreshes. Its output is not automatically the latest atlas data.

## Recorded coverage and release boundaries

These are previously documented snapshots, not counts recomputed on this date.
Keep them attached to their source workflow rather than combining them into a
new purportedly verified release.

| Snapshot | Recorded coverage | Evidence |
| --- | --- | --- |
| November 1 review bundle | 599 point/climate rows; 98 lake candidates using OSM plus HydroLAKES; 36 HydroRIVERS reach attributes; 91 exploratory shoreline profiles | [Original generation report](generation_progress.md) |
| Near-shore MERIT refresh | 258 maxima: 61 stream buffers and 197 lake polygons; 15 missing lake polygons; Onega over budget | [MERIT method and run notes](merit_upstream_area.md) |
| First whole-band shoreline refresh | 211 selected lake sites; 210 with raw band summaries; 133 passing reference checks, 74 with too few inset cells, three with excessive reference range, one deferred large lake | [Whole-band method and run notes](whole_band_shoreline.md) |
| Same shoreline snapshot, all sites | 229 working lake sites: 211 selected polygons plus 18 unmatched; 370 other sites | [Whole-band method and run notes](whole_band_shoreline.md) |

The MERIT near-shore snapshot describes 213 lake sites (197 + 15 + 1), whereas
the later shoreline snapshot describes 229. The shoreline refresh preserves its
input MERIT properties; it does not recompute them for newly selected polygons.
Before packaging a combined release, reconcile habitat labels, polygon IDs and
input checksums by `sample_id`. Do not infer that all 211 selected polygons have
freshly recomputed MERIT values, or treat historical denominators as current.

Passing the shoreline reference checks is an internal quality check, not
independent validation of water elevation or a depth prediction. Lake depth,
shoreline slope and marine-specific collection remain unfinished/deferred.

## Scientific decisions recorded on 2026-11-14

- The thesis used a ring around the lake perimeter. Exact width, elevation
  summary, equation and treatment of island boundaries still need to be
  recovered from the thesis method. Do not assume a variable-width rule.
- Islands may indicate shallower habitat, but this is a biological hypothesis;
  the current inclusion of island shores does not validate that interpretation.
  Preserve enough geometry and method information to compare definitions later.
- The thesis used the maximum drainage-area value, which the project owner
  reports correlated well with outlet drainage area. Retain this as the working
  lake drainage-context metric while checking representative examples.
- Flat lake surfaces make exact routed-cell/outlet interpretation less simple.
  A small outward lake buffer is a possible diagnostic, not an approved method
  change. Establish evidence of missed outlet cells before implementing it.

See the [scientific validation plan](scientific_validation_plan.md) for the
ordered next steps and decision criteria.

## Publication and reproducibility

The download-argument repair is merged in PR #8. Republished downloads have not
been verified in this documentation pass. The mobile viewport proposal remains
separate in PR #7. Use the [viewer guide](public_review_viewer.md) for deployment
steps, retaining the distinction between its original base release and later
lookup/site-metrics assets. Record the actual configured asset IDs, manifests
and successful live checks before declaring a combined release current.

Generated geofiles, raster caches and credentials remain outside Git. Code and
documentation are versioned here; original data and historical releases retain
their identity. Reviewer corrections belong in a separate table by sample ID.
