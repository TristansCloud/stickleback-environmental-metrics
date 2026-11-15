# Whole-band shoreline terrain

See [current status](current_status.md) for the relationship to older review
bundles and [scientific next steps](scientific_validation_plan.md) for proposed
sensitivity comparisons. The November 14 documentation update did not change
band geometry, island treatment, quality thresholds or stored measurements.

Current selected OSM polygons define three disjoint exterior distance bands: 0–50 m, 50–100 m and 100–250 m. Island land is included. Buffer construction uses the same local tangent-plane distances as the earlier exploratory profiles. A native GLO-90 cell is included if its centre falls strictly inside the band. Each valid native cell is counted once; no raster reprojection, resampling, random points or fixed sample cap is used. Cell means and percentiles are unweighted summaries of the included native cells, rather than exact fractional-area statistics.

The water reference is the median of all valid native cell centres at least 90 m inside the selected lake polygon. At least three reference cells and 75% valid coverage are required, and the full reference elevation range must not exceed 5 m. Relative elevation summaries are withheld if this reference is unavailable or unstable. Absolute band elevations and valid/total cell counts remain available. The product is a surface model including vegetation and structures, not bathymetry, shoreline slope or lake depth. The narrowest band is smaller than the nominal raster resolution. Exterior bands can include other waterbodies because no independent land-cover mask is applied.

## Thesis ring and island interpretation

On November 14 the project owner clarified that the thesis used a ring around
the lake perimeter. Its exact width, elevation statistic, water reference,
equation and handling of island boundaries still need to be checked against
the thesis. A variable-width buffer should not be presumed.

Current terrain bands include island land, and current perimeter includes
island shores. Islands may be associated with shallower habitat, as the owner
suggested, but these summaries do not establish that relationship. Keep this
biological interpretation separate from geometric measurement; no single
terrain or shape metric is assumed to capture the full habitat structure.

The three-cell, 75%-coverage and 5 m-range conditions are provisional quality
rules, not independent validation of lake elevation. Relative band heights do
not automatically reproduce the thesis predictor or constitute shoreline slope.
The proposed GLO-90/GLO-30 comparison and any outer-shore/all-shore comparison
are future experiments, not alternate results already available in this release.

## Native-grid collection

The source is the public Copernicus GLO-90 COG archive. Native source grids, tile URLs and SHA-256 hashes are retained. The source uses latitude-dependent pixel widths; each tile is processed on its own grid. Shared border-centred cells belong to a single one-degree tile. Missing source tiles invalidate relative summaries rather than silently accepting a partial band.

Safeguards keep at least 60 GB free, limit each tile download to 8 MB, each lake to 20 tiles and one million read-window cells, and the local projection to a 200 km extent. Very large requests are deferred with an explicit status. These limits are not a sparse-sampling fallback.

Run from an external working directory using the repository Python environment:

```powershell
python "$REPO/scripts/collect_full_band_shoreline.py" --regions merit_regions.geojson --base-metrics merit_maxima.geojson --cache dem_cache/copernicus90 --output whole_band_run --live
python "$REPO/scripts/upload_site_metrics.py" --bundle whole_band_run/RELEASE --project stickleback-507923
```

Use repeated `--sample-id` options for a smoke test. Resume with identical arguments to reuse per-polygon checkpoints. The output retains all 599 original site coordinates, habitat labels, selected lake metrics and MERIT results. Only shoreline measurements and their coverage flag are refreshed. The combined table is uploaded privately; public read access is a separate authorized publishing step. Configure the viewer with this table as its `--merit-asset` and the existing full-outline lookup asset. The App hides the obsolete point-sample layer.

Source: https://copernicus-dem-90m.s3.amazonaws.com/readme.html

## Recorded first full-band release

The first full-band release processes 211 selected lake sites. All 210 within the geometry/cell budget have complete source tiles and raw band summaries. There are 133 accepted lake references, 74 with fewer than three inset native cells, three with water-reference elevation ranges above 5 m, and one deferred large lake (Onega). Across all 599 sites there are also 18 lake sites without selected polygons and 370 non-lake sites. The cache contains 63 tiles totaling approximately 187 MB. The release preserves the earlier MERIT results exactly.

These are previously recorded counts; they were not recomputed during the
documentation update. "Accepted" means passing the reference checks above.
It does not mean independently verified water elevation or validated depth.
The 211 selected polygons and 229 working lake sites must not be substituted
for the denominators in an older MERIT run without reconciling its inputs.
