# Whole-band shoreline terrain

Current selected OSM polygons define three disjoint exterior distance bands: 0–50 m, 50–100 m and 100–250 m. Island land is included. Buffer construction uses the same local tangent-plane distances as the earlier exploratory profiles. A native GLO-90 cell is included if its centre falls strictly inside the band. Each valid native cell is counted once; no raster reprojection, resampling, random points or fixed sample cap is used. Cell means and percentiles are unweighted summaries of the included native cells, rather than exact fractional-area statistics.

The water reference is the median of all valid native cell centres at least 90 m inside the selected lake polygon. At least three reference cells and 75% valid coverage are required, and the full reference elevation range must not exceed 5 m. Relative elevation summaries are withheld if this reference is unavailable or unstable. Absolute band elevations and valid/total cell counts remain available. The product is a surface model including vegetation and structures, not bathymetry, shoreline slope or lake depth. The narrowest band is smaller than the nominal raster resolution. Exterior bands can include other waterbodies because no independent land-cover mask is applied.

The source is the public Copernicus GLO-90 COG archive. Native source grids, tile URLs and SHA-256 hashes are retained. The source uses latitude-dependent pixel widths; each tile is processed on its own grid. Shared border-centred cells belong to a single one-degree tile. Missing source tiles invalidate relative summaries rather than silently accepting a partial band.

Safeguards keep at least 60 GB free, limit each tile download to 8 MB, each lake to 20 tiles and one million read-window cells, and the local projection to a 200 km extent. Very large requests are deferred with an explicit status. These limits are not a sparse-sampling fallback.

Run from an external working directory using the repository Python environment:

```powershell
python "$REPO/scripts/collect_full_band_shoreline.py" --regions merit_regions.geojson --base-metrics merit_maxima.geojson --cache dem_cache/copernicus90 --output whole_band_run --live
python "$REPO/scripts/upload_site_metrics.py" --bundle whole_band_run/RELEASE --project stickleback-507923
```

Use repeated `--sample-id` options for a smoke test. Resume with identical arguments to reuse per-polygon checkpoints. The output retains all 599 original site coordinates, habitat labels, selected lake metrics and MERIT results. Only shoreline measurements and their coverage flag are refreshed. The combined table is uploaded privately; public read access is a separate authorized publishing step. Configure the viewer with this table as its `--merit-asset` and the existing full-outline lookup asset. The App hides the obsolete point-sample layer.

Source: https://copernicus-dem-90m.s3.amazonaws.com/readme.html

## Current release

The first full-band release processes 211 selected lake sites. All 210 within the geometry/cell budget have complete source tiles and raw band summaries. There are 133 accepted lake references, 74 with fewer than three inset native cells, three with water-reference elevation ranges above 5 m, and one deferred large lake (Onega). Across all 599 sites there are also 18 lake sites without selected polygons and 370 non-lake sites. The cache contains 63 tiles totaling approximately 187 MB. The release preserves the earlier MERIT results exactly.
