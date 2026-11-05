# MERIT upstream drainage area

The current upstream-area product uses MERIT Hydro v1.0.1, band upa in square kilometres, on its native 3-arc-second grid.

Stream sites use the maximum over native cell centres within 150 m of the original coordinate. Lake sites use the maximum over native cell centres inside the selected full lake polygon, retaining holes. The product records the method, number of valid cells and selected polygon source. Nearby tributaries and downstream cells can dominate the regional maximum.

The preflight lake budget is 1,000,000 cells in the polygon bounding box. This conservative bound avoids sending oversized lake jobs. The reducer also sets maxPixelsPerRegion to the budget. Lakes exceeding the bound receive lake_pixel_budget_exceeded and a null value. Tiny or entirely masked regions receive no_native_cells. Lakes without a selected full polygon receive missing_lake_polygon. Marine, transition and unresolved habitat records receive not_applicable.

From the same external working directory used for the closest-water lookup, run:

```sh
python "$REPO/scripts/closest_water_599.py" "$REPO" - 1500 osm_replica_cache/site_features.json
python "$REPO/scripts/collect_merit_maxima.py" --regions merit_regions.geojson --sites "$REPO/data/ee_full_review/source_2026-11-01/stickleback_full_review_v1.csv" --output merit_maxima --project stickleback-507923 --upload
```

The collector caches reductions in groups of 20 and identifies results by input checksum, extraction rule and lake cell budget. It exports a separate private table with exactly 599 site records. Supply the verified asset path to configure_ee_full_review.py via --merit-asset, along with --lookup-asset for the vector overlay. The viewer's upstream-area section uses the new MERIT fields, and the current CSV omits earlier river fields.

The November 5 run computed 61 stream buffers and 147 lake polygons. Lake Onega (S0097) exceeded the budget. Sixty-five lake sites lacked selected polygons. The table contains explicit statuses for every original site.

[Earth Engine MERIT Hydro catalog](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)

[Earth Engine reduceRegions](https://developers.google.com/earth-engine/apidocs/ee-image-reduceregions)
