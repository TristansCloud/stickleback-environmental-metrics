# Public full-dataset reviewer App

## Download-button repair (2026-11-11)

The published `stickleback-atlas` App was tested directly on 2026-11-11.
Clicking **Create full-precision dataset download links** immediately raised
`TypeError: e.format.toUpperCase is not a function` in the browser console and
left the button disabled on “Preparing links”. This was a JavaScript argument
error, before any dataset download, rather than evidence of slow sampling.

`FeatureCollection.getDownloadURL` accepts positional arguments or one named
options object. The previous calls mixed an options object with a second,
positional callback, causing the object to be interpreted as the format string.
The callback now lives inside the options object. Geometry downloads also use
the documented `geojson` format instead of `GEO_JSON` (a batch-export spelling).
The three links prepare independently, report errors by file, and allow retry
after 30 seconds with late responses ignored. The timeout covers link creation,
not the subsequent file transfer after a link is opened.

Offline regression checks (Node.js required):

```sh
node --test tests/ee_downloads.test.cjs
node --check apps/earth_engine_validation/ee_full_review_app.js
```

To apply this repair to the existing published App, replace only the block from
`var downloadStatus =` through the end of the `var download = ui.Button(...)`
declaration in the deployed Code Editor script with that block from
`apps/earth_engine_validation/ee_full_review_app.js`. Keep the deployed asset
constants and map layout. Run the script, create the links, open the CSV and
both GeoJSON files, then update the existing App through **Apps**. Verify again
at the public URL while signed out, including 599 CSV rows and original IDs.
No asset upload, permission change or environmental rerun is needed for this
repair. The source repair and offline tests alone do not update the live App;
successful live downloads after republishing remain to be verified.

This is the new public viewer for the full environmental review. It is separate
from the historical 40-site private pilot and lake-QC Apps. Public sharing was
requested by the project owner on 2026-11-01. The older restricted Apps and
registry are not changed by this workflow.

## Implementation and current release

`apps/earth_engine_validation/ee_full_review_app.js` supports all 599 original
sites, search and habitat/coverage filters, click selection, shareable `site` URL
state, climate charts, source properties, browser-only reviewer notes, and
full-precision CSV/GeoJSON download links. Original coordinates stay unchanged.
Lake/river identity and habitat classes remain provisional; missing values are
not converted to zero. MERIT sample-cell values remain separate from HydroRIVERS
reach-outlet attributes. Depth remains unestimated.

The source is the extracted `stickleback_review_2026-11-01.zip`, whose own
manifest checksums are verified before conversion. Current prepared release:

- `ee_full_review_v1_3d571ff57e659c91`
- 599 sites, 98 candidate lake polygons, 153 river-evidence features.
- 6,984 shoreline sampling locations from the stored plan and sample elevations,
  including six unstable/insufficient profiles. These locations are not
  independent DEM cells. One unsupported lake has no sampling plan.
- Every feature carries the release ID. Sites also carry source-bundle checksum,
  stored measurements/status, and point/climate/shoreline source metadata.

All generated data, configured App copies, and upload records belong under
ignored `data/ee_full_review/`. Do not commit geofiles, review CSVs or rasters.

## Prepare and configure offline

From the repository root with the ZIP already extracted:

```sh
python -m pip install -e '.[earth-engine,test]'
python scripts/prepare_ee_full_review.py --bundle /path/to/extracted-review
python scripts/configure_ee_full_review.py \
  --bundle data/ee_full_review/ee_full_review_v1_3d571ff57e659c91 \
  --asset-parent projects/stickleback-507923/assets/stickleback_validation \
  --output data/ee_full_review/ee_full_review_app_configured.js
```

Preparation verifies all source checksums, site IDs, original coordinates and
ecotypes, and the ordering/count of shoreline coordinates versus elevations.
It retains numerical values without display rounding, keeps IDs as strings,
preserves null, rejects non-finite values, and refuses to change an existing
immutable prepared release. The prepared manifest records collection checksums.
Different source bundles generate a different release name.

## Upload, verify, and share

No authentication is bundled. Sign in using the project owner's authorized
Google account; never commit credentials or paste them into chat. The existing
private parent folder must already exist.

```sh
earthengine authenticate
# Offline plan first; no network without --upload or --verify.
python scripts/upload_ee_full_review.py \
  --bundle data/ee_full_review/ee_full_review_v1_3d571ff57e659c91 \
  --project stickleback-507923 \
  --asset-parent projects/stickleback-507923/assets/stickleback_validation

# Start four private table exports. Keep the resulting upload_tasks.json.
python scripts/upload_ee_full_review.py \
  --bundle data/ee_full_review/ee_full_review_v1_3d571ff57e659c91 \
  --project stickleback-507923 \
  --asset-parent projects/stickleback-507923/assets/stickleback_validation --upload
```

Wait for all four exports to complete. The uploader refuses an existing release
folder or upload record; inspect partial failures instead of repeating exports
or replacing old evidence. `upload_tasks.json` ties verification to the tasks,
asset paths and local manifest actually uploaded.

```sh
python scripts/upload_ee_full_review.py \
  --bundle data/ee_full_review/ee_full_review_v1_3d571ff57e659c91 \
  --project stickleback-507923 \
  --asset-parent projects/stickleback-507923/assets/stickleback_validation --verify

# This explicitly makes ONLY this release's four tables publicly readable.
python scripts/upload_ee_full_review.py \
  --bundle data/ee_full_review/ee_full_review_v1_3d571ff57e659c91 \
  --project stickleback-507923 \
  --asset-parent projects/stickleback-507923/assets/stickleback_validation \
  --verify --share-public
```

Verification must pass for every export before any sharing starts. It checks
completed tasks, cloud feature counts and release IDs, and the upload manifest.
It does not grant project IAM, publish an App, change the old pilot registry or
modify the original review bundle. If a sharing request fails partway through,
inspect the printed successes; do not assume the release is wholly private.

Open the configured JavaScript in the Earth Engine Code Editor and run it.
Publish using **Apps → New App**, select `stickleback-507923`, choose the script,
and leave Google Group restriction off. Record the actual URL returned by
Google; do not invent a URL from the project or proposed App name.

## Visual acceptance checks before declaring publication complete

1. Verify 599 sites, including unresolved/marine records. Filter lake polygon
   available → 98 sites; river attributes → 36; shoreline profile → 91.
2. Inspect S0074 Þingvallavatn: candidate shoreline/islands, original point,
   climate charts, full-precision properties, missing depth, and stored sampling
   locations (toggle the sampling layer in Layers).
3. Inspect a stream with river evidence, an unmatched lake and a marine site.
   No marine elevation should be described as bathymetry, and no reach-outlet
   area should be described as sample-cell drainage.
4. Switch sites quickly; stale responses must not overwrite the selected site.
   Click selection respects the current filter. Open a `site`-parameter link.
5. Switch Google hybrid/satellite/terrain and the optional Sentinel-2 layer.
   Clear composites use the selected full calendar year, Cloud Score+ ≥0.60,
   median RGB at native 10 m, and a bounded 20 km site region. Gaps can reveal
   the Google basemap beneath. Cloud masking does not guarantee gap-free,
   cloud-free or snow-free imagery. Annual composites mix seasons.
6. Check map layer toggles, the yellow outline for the selected lake candidate,
   legends and the original-coordinate marker.
7. Download CSV and lake/river GeoJSON; verify counts, nulls, units and original
   IDs/coordinates. Source values retain their full stored precision.
8. Open the actual published URL while signed out; all four evidence assets
   and imagery must render. Check the layout at desktop and narrow widths.
   Notes are browser-only and must be copied before switching sites.

UI distances display metres or kilometres to three decimals; area uses hectares
to two decimals; elevation/relative elevation uses whole metres; temperature
uses one decimal. Precipitation is mm/day to two decimals. Rounding is to nearest,
not truncation, and communicates no improvement in source accuracy.

## Deployment status

The implementation, offline prepared release and tests are ready. At preparation
time this workspace had no Earth Engine credentials and the browser was signed
out of Google. No new cloud assets, public ACLs or public App URL have been
created or verified yet. Live API/UI and signed-out visual acceptance remain
required before this is described as a published viewer.

Primary platform references:

- [Earth Engine Apps and publishing](https://developers.google.com/earth-engine/guides/apps)
- [Google basemap types](https://developers.google.com/earth-engine/apidocs/ui-map-setoptions)
- [Cloud Score+ Sentinel-2 example](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED)
