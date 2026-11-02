# One lake lookup: Þingvallavatn

Pending identity and neighbouring-polygon questions are tracked in the
[manual QC queue](osm_manual_qc.md). Batch discovery records every returned
object in `candidate_discovery.jsonl`, including unselected candidates.

Use sample **S0074**, latitude **64.18656**, longitude **-21.08836**.
Overpass uses latitude,longitude; GeoJSON and GIS geometry use longitude,latitude.
The input name suggests a lake; it does not establish polygon identity.

## Live lookup

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_lake_polygon_pilot.py --live-osm --sample-id S0074 --timeout-seconds 30 --output-dir data/lake_lookup_S0074
```

The current runner first makes a 500 m tags-only discovery query. It retrieves
up to three ranked objects' complete geometry through the core OSM API. If no
containing polygon is found, it tries enclosing-area discovery and then a
2000 m tags-only query. Nearby geometry must still contain the sample.

The original single-lake trial used enclosing-area discovery first, which
avoids requiring a shoreline within a small radius of a large lake:

```text
[out:json][timeout:25];
is_in(64.18656,-21.08836)->.areas;
(way(pivot.areas)[natural=water];rel(pivot.areas)[natural=water];
 way(pivot.areas)[landuse=reservoir];rel(pivot.areas)[landuse=reservoir];);
out tags;
```

Discovery found relation 37637. This original Overpass geometry query remains
valid, but the current batch obtains geometry through core OSM `/full.json`:

```text
[out:json][timeout:25];relation(id:37637);out body geom;
```

`body` retains tags, way nodes and relation members; `geom` supplies coordinates.
The previous `out geom tags` query suppressed member geometry and caused
`missing_outer_ring` rejection even though the lake existed.
See the [Overpass output reference](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL#Print_(out)).

Check `natural=water`, `water=lake`, name evidence, complete closed outer rings,
island holes and containment. Review the shoreline and sample location before
accepting identity. The runner currently also considers ponds, reservoirs,
basins and unspecified water; these are candidates, not certified lakes.
The logged search radius describes discovery, not a clipped geometry window.

## Local Geofabrik lookup

The existing Iceland extract is in university OneDrive. Its README records
OSM data as of **2025-09-12T20:21:01Z**, downloaded from
[Geofabrik Iceland shapefiles](https://download.geofabrik.de/europe/iceland-latest-free.shp.zip).
Keep the `.shp`, `.shx`, `.dbf`, `.prj` and `.cpg` together.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[local-osm]"
.\.venv\Scripts\python.exe scripts/lookup_local_osm_water.py --shapefile 'C:\Users\trist\OneDrive - Loyola University Chicago\Marius\global_lake_polygons\Europe\iceland_openstreetmap\gis_osm_water_a_free_1.shp' --latitude 64.18656 --longitude -21.08836 --site-name Þingvallavatn --output data/lake_lookup_S0074/geofabrik_candidate.geojson
```

This script checks the CRS, scans bounding boxes, checks polygon validity and
point containment including holes, and returns every containing water or
reservoir candidate. Boundary points are flagged. It reads the source file
without changing it. The waterways file contains lines and is rejected.

The free export's `fclass=water` groups lakes with other water bodies and loses
the detailed `water=lake/pond/...` tag. `osm_id` alone does not establish whether
an object was a way or relation, and may repeat across geometry records.
See [Geofabrik's schema](https://download.geofabrik.de/osm-data-in-gis-formats-free.pdf).
Do not infer object type from the size of the numeric ID.

Recommended next pipeline: record region, snapshot and file checksum; build a
local spatial index for batch lookup; retain all overlaps, names and source
record IDs; verify detailed tags and object identity; check extract-edge clipping
and disconnected pieces before accepting whole-lake metrics. For strict lake
classification fully offline, use a regional OSM PBF with preserved tags and
assembled multipolygons. Keep reservoirs and ponds separately labelled.
Geofabrik is another delivery of OSM, not an independent hydrology dataset.

## Observed result, 2026-10-07 UTC

| Check | Live Overpass | Local September 2025 extract |
|---|---|---|
| OSM ID | relation 37637 | 37637; object type absent |
| Name | Þingvallavatn | Þingvallavatn |
| Classification | natural=water, water=lake | fclass=water, code=8200 |
| Sample inside | Yes | Yes, away from boundary |
| Candidate count | 1 | 1 |
| Area | 82.309416 km² | 82.315044 km² |
| Shoreline, including islands | 96.09538 km | 96.04431 km |

Areas use the project's spherical approximation. The local metrics above are
an exploratory comparison, not a certification of extract completeness.
Local area is approximately 0.00684% higher; geometries are not identical.
The comparison does not identify the cause of the differences.

Raw Overpass responses, live CSV/GeoJSON, metadata and the local candidate
GeoJSON are saved under `data/lake_lookup_S0074/` and ignored by Git. Live
geometry query hash: `a88f001b6f8cc5846659f06b`.
Rerunning uses saved responses where available; omit `--live-osm` to replay
without network access. Open the GeoJSONs alongside the sample point in QGIS
for the final shoreline and identity review. Preserve OSM contributor/ODbL
attribution when sharing derived polygons.

## Additional bounded trials, October 6, 2026 Toronto time

The main Overpass endpoint returned HTTP 504 for South Twin Lake's enclosing
area query and Paxton Lake's geometry query. These are retrieval failures,
not evidence that OSM has no polygon. An alternative Private.coffee endpoint
failed DNS resolution on this machine. The runner now accepts `--endpoint`;
use separate output directories for different endpoints so cached responses
are not confused with a fresh comparison.

Smaller 500 m tags-only searches on the main endpoint succeeded for South
Twin Lake, Mývatn and Lake Kursinka. Paxton's successful enclosing-area
response already supplied its identity. Known-object full geometry reads
through the core OSM API succeeded for all four lakes:

| Input sample | Object | Full polygon contains point | Area km² | Name evidence |
|---|---|---|---|---|
| S0512 South Twin Lake | way 352410633 | Yes | 0.418104 | Agrees |
| S0364 Paxton Lake | way 299621234 | Yes | 0.171748 | Agrees |
| S0044 Mývatn-mud | relation 191040 | Yes | 38.782006 | Differs: input includes `-mud` |
| S0202 Lake Kursinka | way 107465668 | Yes | 2.656695 | Differs: OSM name is `Курсинка` |

South Twin's discovery also returned Wickiup Reservoir, relation 17060302.
Its full polygon did not contain the sample and its `water=reservoir` tag
distinguished its type. No lake metrics were accepted for that object.
Name differences above remain review flags; the code does not automatically
strip site suffixes or certify transliterations.

The reusable known-object helper can replay saved geometry offline:

```powershell
.\.venv\Scripts\python.exe scripts/fetch_osm_lake_object.py --sample-id S0364 --osm-type way --osm-id 299621234 --output-dir data/lake_lookup_trials_20261006/S0364
```

Add `--live-osm` to authorize a cache-missing read. This uses
`GET https://api.openstreetmap.org/api/0.6/way/299621234/full.json` and resolves
way node references into geometry. It also supports ordinary multipolygon
relations; missing nodes/members and non-way relation members are rejected.
See the [OSM full-object API reference](https://wiki.openstreetmap.org/wiki/API_v0.6#Full:_GET_/api/0.6/[way|relation]/#id/full).
Object modification timestamps describe OSM edits, not download dates.

At the time of these initial trials this was a manual fallback. The expanded
pilot now integrates core OSM geometry retrieval as its normal geometry route.
Keep Overpass for coordinate/tag discovery and use the core API only for
bounded reads of known objects. A 500 m search can miss lakes whose shores
are farther away; preserve enclosing-area discovery for those cases.
Trial raw responses, result JSON and full GeoJSONs are retained under
`data/lake_lookup_trials_20261006/`, ignored by Git.

## Durable 40-site batch

```powershell
.\.venv\Scripts\python.exe scripts/run_lake_polygon_pilot.py --live-osm --count 40 --output-dir data/lake_lookup_40_20261006 --timeout-seconds 30 --request-delay-seconds 2 --retries 1 --max-requests 320 --max-failures 3
```

The selected 40 IDs remain identical to the baseline snapshot, including the
three pond-name cases. OSM classification is reported separately in
`osm_waterbody_type`; ponds and reservoirs are not relabelled as lakes.

Network reads share a two-second gap, have one retry for transient errors,
and stop after three consecutive sites with retrieval failure or the configured request
budget. HTTP 429 receives a 30-second backoff. The live batch began with a
two-second gap and was resumed with five seconds after server throttling;
the final three incomplete sites were retried with ten seconds between requests.
The transport enforces a hard 30-second total deadline, including response reads.
Longer numeric or HTTP-date Retry-After values are honored, and cooldowns carry
across stages even when the last permitted retry fails. Long waits are split
into intervals of at most 60 seconds.
completed checkpoints and cached reads were reused. Overpass responses with error remarks are failures, not empty successful
searches. A failed discovery stage can proceed to the next bounded stage.
Raw cache keys include the endpoint and request contents.

Every completed site writes an atomic checkpoint and refreshes the summary
CSV, selected-polygon GeoJSON and metadata. Rerun the same command to resume:
completed candidate/no-polygon/unresolved sites reuse checkpoints; retrieval
failures are reevaluated. Input hashes, selection, endpoint and candidate limits
must match the output manifest. Use a new output directory for changed inputs
or policy. `--no-resume` reevaluates every site from cached/network evidence;
omitting `--live-osm` prevents new network requests. The request budget applies
per invocation; request logs retain earlier attempts.

The geometry cap is three ranked objects per discovery stage; all returned
objects are retained in discovery logs. Truncation and failed competing reads
set review flags. Exhausting the bounded searches does not establish that no
water polygon exists outside the searched area.

Outputs:

- `selection_manifest.json`: source hash and exact IDs/policy.
- `lake_polygon_pilot.csv` and `.geojson`: candidate results, never certified habitat identities.
- `candidate_discovery.jsonl`: all objects returned by each successful search.
- `candidate_outcomes.jsonl`: full geometry, containment and rejection outcomes for evaluated objects.
- `candidate_polygons/`: complete evaluated polygons, including rejected neighbours.
- `requests.jsonl`, raw response/metadata caches and `checkpoints/`: provenance and resume evidence.
- `run_metadata.json`: processed/pending IDs, request counts and stop state.

Generate a readable review report and point layer from the completed results:

```powershell
.\.venv\Scripts\python.exe scripts/report_lake_lookup.py --run-dir data/lake_lookup_40_20261006 --output docs/lake_lookup_40_2026-10-06.md
```

The implementation is in `src/enviro_data/lake_lookup.py`; the script keeps
the deterministic selection and CLI. Existing trial responses were imported
with their source-cache references to avoid repeating successful reads.
