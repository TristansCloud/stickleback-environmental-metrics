# MERIT upstream drainage area

See [current project status](current_status.md) for release boundaries and the
[validation plan](scientific_validation_plan.md#5-check-merit-maxima-before-changing-their-extraction-region)
for the next scientific checks. No extraction rule changed in the November 14
documentation update.

The current upstream-area product uses MERIT Hydro v1.0.1, band upa in square kilometres, on its native 3-arc-second grid.

Stream sites use the maximum over native cell centres within 150 m of the original coordinate. Lake sites use the maximum over native cell centres inside the selected full lake polygon, retaining holes. The product records the method, number of valid cells and selected polygon source. Nearby tributaries and downstream cells can dominate the regional maximum.

## Interpretation and thesis context

The lake maximum is the working measure of upstream drainage context for the
lake: modelled contributing area, in km², rather than water discharge. The
project owner reports using the maximum in the thesis with good agreement to
outlet drainage area. That is relevant prior experience, not a newly measured
validation statistic for this dataset.

Flat lake surfaces can make interpretation of the modelled drainage path and
exact outlet cell less straightforward. MERIT's routed accumulation is not a
measurement of water circulation across the lake. A point sample, a maximum
within the lake and the value at a verified outlet are distinct extraction
definitions even when their numerical values agree.

The current collector retains the maximum and valid-cell count, but not the
coordinates of the cell producing the maximum, its flow direction or verified
channel connectivity. `merit_status=ok` records a successful reduction, not
verified outlet identity. A stream buffer can include a larger neighbouring
channel or a cell downstream of a confluence.

Keep the unbuffered lake-polygon maximum as the current method. A small outward
buffer is only a proposed diagnostic if representative outlet checks show the
polygon misses relevant native cells. Establish that failure first; a larger
buffered maximum alone would not demonstrate a better lake drainage estimate.
No buffer, maximum-cell diagnostic or new collection was implemented here.

## Collection and explicit statuses

The preflight lake budget is 1,000,000 cells in the polygon bounding box. This conservative bound avoids sending oversized lake jobs. The reducer also sets maxPixelsPerRegion to the budget. Lakes exceeding the bound receive lake_pixel_budget_exceeded and a null value. Tiny or entirely masked regions receive no_native_cells. Lakes without a selected full polygon receive missing_lake_polygon. Marine, transition and unresolved habitat records receive not_applicable.

From the same external working directory used for the closest-water lookup, run:

```sh
python "$REPO/scripts/closest_water_599.py" "$REPO" - 1500 osm_replica_cache/site_features.json
python "$REPO/scripts/collect_merit_maxima.py" --regions merit_regions.geojson --sites "$REPO/data/ee_full_review/source_2026-11-01/stickleback_full_review_v1.csv" --output merit_maxima --project stickleback-507923 --upload
```

The collector caches reductions in groups of 20 and identifies results by input checksum, extraction rule and lake cell budget. It exports a separate private table with exactly 599 site records. Supply the verified asset path to configure_ee_full_review.py via --merit-asset, along with --lookup-asset for the vector overlay. The viewer's upstream-area section uses the new MERIT fields, and the current CSV omits earlier river fields.

## Recorded run snapshots

These counts describe their original inputs, not one reconciled current release.

The November 5 run computed 61 stream buffers and 147 lake polygons. Lake Onega (S0097) exceeded the budget. Sixty-five lake sites lacked selected polygons. The table contains explicit statuses for every original site.

[Earth Engine MERIT Hydro catalog](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)

[Earth Engine reduceRegions](https://developers.google.com/earth-engine/apidocs/ee-image-reduceregions)

Near-shore lake proposals use the same full-polygon maximum, with lake_match_method, lake_shore_distance_m and lake_name_evidence attached to the result. The original coordinates are retained.

The near-shore release computed 258 upstream-area values (61 streams and 197 lakes). Fifteen lake sites still lack selected polygons and Lake Onega still exceeds the cell budget. Misty Lake (S0290) uses the named polygon 153.61 m from the original point and has a maximum upstream area of 10.536004066467285 km².

This near-shore snapshot accounts for 213 working lake sites. The later
whole-band shoreline notes account for 229; that refresh preserves input MERIT
properties without recalculating maxima. Reconcile labels, polygon identity
and input checksums by sample ID before treating these snapshots as one release.
