# Earth Engine pilot validation viewer

`ee_pilot_validation_app.js` is a Code Editor template for a restricted human
inspection of the deterministic 40-site pilot. It is not a pipeline runner,
analysis tool, or data-acquisition tool.

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
