# Private Earth Engine lake-review upload, 2026-10-07

The owner explicitly approved uploading the frozen bundle to Earth Engine project
`stickleback-507923`. All three table export tasks completed successfully.

Release folder: `projects/stickleback-507923/assets/stickleback_validation/ee_lake_review_v1_3c2c0cdae927cca6`.

| Collection | Verified features | Completed export task |
| --- | ---: | --- |
| lake_sites | 40 | RFFYB2QWBFKQJIAHS2L4VJPR |
| selected_candidates | 24 | MP5VM2SOR7AUCFXBBUIOCTIB |
| evaluated_polygons | 83 | 7MBA5YSCRGZ7N3EX7V7AROFN |

Every uploaded feature carries release ID `ee_lake_review_v1_3c2c0cdae927cca6`.
The uploader verified all collection checksums before starting exports.
All collections have no explicit readers and no public-read flag; no sharing
permissions were changed. Project-level IAM access still applies.

All 40 original sample IDs and point coordinates were checked against the frozen
local GeoJSON. Earth Engine returns minor floating-point serialization differences
(maximum 2.1316282072803006e-14 degrees), below the 1e-12-degree check tolerance.
The frozen source files retain the exact input coordinate values.

`apps/earth_engine_validation/ee_lake_review_app.js` now points to these assets.
JavaScript syntax validation passed. Code Editor rendering and manual review
controls still need visual verification; the App has not been published.
The older environmental-pilot registry and published App were not advanced.

Manual QC remains required for habitat identity, reservoir neighbours, shared
borders and connectivity. No new OSM or Overpass requests were made for this upload.
