# Earth Engine pilot validation viewer

## New lake polygon review

`ee_lake_review_app.js` provides a dedicated, read-only view of the new lake-only
lookup run. Its site selection differs from the original environmental pilot.
It shows original coordinates, selected candidates and all evaluated polygons,
including rejected reservoirs and neighbours. Discovered objects whose geometry
was not retrieved remain visible as stored `discovery_evidence` on the site.
Manual controls record habitat, identity and neighbour relationships; copy each
review JSON before changing sites. These controls do not save anything.

Prepare the frozen collections offline:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_ee_lake_assets.py --run-dir data/lake_lookup_40_20261006
```

The prepared release is
`data/ee_app_validation/ee_lake_review_v1_3c2c0cdae927cca6/`:
40 `lake_sites`, 24 `selected_candidates`, and 83 `evaluated_polygons`.
Its manifest records input and output checksums. Coordinates and polygon
geometry remain unchanged. Nested properties are JSON strings for portable EE
table properties; null remains null. Generated geometry bundles stay local and
ignored by Git. Identical reruns reuse the bundle; changed inputs create a new
release and altered existing bundles are rejected.

The three private cloud assets were uploaded and verified on 2026-10-07 at
`projects/stickleback-507923/assets/stickleback_validation/ee_lake_review_v1_3c2c0cdae927cca6`.
The viewer `ROOT` is configured for this release. The App has not been published
or visually checked in the Code Editor. See the [upload record](../../docs/ee_lake_review_upload_2026-10-07.md).

For a future release, install the existing `earth-engine` optional dependency and
authenticate with the authorized Earth Engine account. Use an existing private
asset parent; the already uploaded release below must not be rerun:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[earth-engine]'
.\.venv\Scripts\earthengine.exe authenticate
.\.venv\Scripts\python.exe scripts/upload_ee_lake_assets.py --project stickleback-507923 --asset-parent projects/stickleback-507923/assets/stickleback_validation --bundle data/ee_app_validation/ee_lake_review_v1_3c2c0cdae927cca6
```

The upload command verifies checksums, creates a new release folder and starts
three table export tasks. It refuses existing release folders, leaves access
permissions unchanged, and prints task IDs. If a task fails, inspect its error;
do not rerun against or overwrite a partial immutable release. After all tasks
complete, set `ROOT` in `ee_lake_review_app.js` to the printed release folder and
run it in the Code Editor. Verify 40 sites, 24 selected candidates and 83 evaluated
polygons; inspect S0512 South Twin Lake and its Wickiup Reservoir neighbour,
S0074 Þingvallavatn, and an unresolved site. Check that manual review JSON carries
the selected site, release ID and OSM object ID. Satellite imagery dates may
differ from the OSM snapshot. Shared borders and connectivity need visual QC;
the viewer does not calculate or certify them.

Publish with the restricted access and asset-sharing procedure below. This
dedicated viewer uses no Copernicus/MERIT joins and does not replace the older
environmental pilot's registry. Earth Engine's documented
[table asset export](https://developers.google.com/earth-engine/guides/exporting_tables)
and [UI widgets](https://developers.google.com/earth-engine/guides/ui_widgets)
are the interfaces used here.

`ee_pilot_validation_app.js` is a Code Editor template for a restricted human
inspection of the deterministic 40-site pilot. It is not a pipeline runner,
analysis tool, or data-acquisition tool.

`ee_pilot_validation_app_current.js` is the App source to publish when the
viewer should follow the approved **current** release. Unlike the original
immutable-release template, it never needs its source constants edited for a
compatible new run. Its only stable asset is the one-feature registry
`projects/stickleback-507923/assets/stickleback_validation/app_current/validation_app_registry_current`.
The registry points to exactly three immutable evidence collections:

| Stable App ID | Purpose |
| --- | --- |
| `pilot_output_asset_id` | immutable current release's stored pilot values and run/provenance fields |
| `osm_matches_asset_id` | immutable current release's frozen OSM match evidence |
| `copernicus_windows_asset_id` | immutable current release's exact Copernicus-window footprints |

The registry is the mutable *release-channel pointer*, not source data. Its
values must name one reviewed immutable release; no live Overpass call, raster
sampling, or pipeline recomputation is permitted while updating it. Immutable
releases retain names such as
`ee_app_validation_assets_v3_4e20cbe056b676f2`, are never overwritten, and
remain the audit record for historical validation.

## Advancing the current release channel

The Code Editor script remains unchanged for a compatible expanded run. An
authorized release process must instead:

1. Produce and validate a new immutable three-collection evidence bundle.
2. Verify its schema is compatible with the current viewer, its per-feature
   release ID/checksums/provenance are present, and no-data values remain null.
3. Write one replacement registry feature containing the three immutable asset
   IDs, `app_release_id`, `registry_checksum_sha256`, approval time, and
   approver. Never mix collections from releases.
4. Replace the registry as one controlled release operation, retaining every
   old immutable bundle.
5. Run the published App and check expected count, one known site, release ID,
   and the three displayed evidence layers before declaring the channel current.

If new data sources require only additional stored properties, a compatible
viewer can display them after a one-time script enhancement; subsequent runs
still advance the registry rather than editing constants. The current script
also shows previously unknown stored point properties automatically. If geometry,
join keys, or evidence semantics change incompatibly, publish a new versioned
viewer/release channel and keep the old App available for its prior audit
record. The App always reads frozen copies and never recalculates or fetches
live evidence.

`app_current/` is only an organizational asset path; it is not a folder that
Earth Engine can load as a source. The registry is the explicit, fixed contract
that makes expansion work without future source edits.

## What it reads

The three constants at the top of the script intentionally contain placeholders.
Replace them only with immutable, versioned FeatureCollection assets prepared
from the completed pilot run:

| Constant | Geometry | Required evidence |
| --- | --- | --- |
| `pilotOutput` | pilot points | input coordinates/ecotype; stored terrain, MERIT, hydrology, run, runtime, and provenance properties |
| `osmMatches` | selected matched water geometry | `sample_id`, match fields, snapshot timestamp/checksum, and status; omit geometry only when no match existed |
| `copernicusWindows` | exact 3×3-window footprint polygon | `sample_id`, window checksum, source/retrieval metadata, status, and resolution |

The property names consumed by the viewer are visible in `renderDetails`.
Missing properties display as `null`; do not replace genuine no-data values with
zero during asset preparation. Every pilot-output feature should carry the run
ID/version and the timing definition. Use a dated/versioned asset path, never a
mutable alias. The map therefore shows the exact evidence used by the pilot,
not a subsequently refreshed source.

## Manual deployment checklist

No asset, App, group, sharing, or permission operation is performed by this
repository or this template. After the necessary evidence assets have been
created and checked by an authorized person:

1. Copy the JavaScript into a new Earth Engine Code Editor script.
2. Replace the three placeholder IDs with the approved frozen asset IDs.
3. Run it in the Code Editor and verify that it lists exactly 40 site IDs and
   that `S0002` displays its expected stored values.
4. Publish only after the owner has explicitly set restricted App access to the
   intended one-member group. Share each frozen asset directly with the
   published App identity as required for the App to read it; this is separate
   from reviewer-group access and does not require public access. Do not make
   the App or its assets public.

## Reviewer behavior

Select a site or click a nearby point to inspect the point, matched OSM feature,
Copernicus window, stored terrain/MERIT values, and provenance. The review
controls create JSON in the browser panel only. Nothing is saved, exported,
submitted, or written by the App; reviewers must copy the text manually into
their separately approved review record. Closing or reloading the page loses
the review text.

The viewer contains no environmental calculations and no calls to a live OSM
service. It must remain read-only: do not add asset writes, task exports,
external fetches, or recalculation logic to this validation App.
