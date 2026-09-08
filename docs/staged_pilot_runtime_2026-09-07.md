# Staged pilot runtime report — 2026-09-07

The guarded progression completed successfully with the authenticated Earth
Engine project `stickleback-507923`:

| Stage | Rows | Wall time | CPU time | Peak Python allocation | Peak RSS |
|---|---:|---:|---:|---:|---|
| 5-site gate | 5 | 21.053 s | 2.969 s | 8.58 MB | unavailable (`psutil` not installed) |
| 40-site pilot | 40 | 132.532 s | 19.047 s | 18.88 MB | unavailable (`psutil` not installed) |

Earth Engine client round-trip (`reduceRegion.getInfo`) time was 7.693 s for
the five-site gate and 46.279 s for the 40-site run. These are client timings;
they do not represent Earth Engine server compute or EECU. Copernicus COG
client/cache elapsed time was 13.336 s and 86.132 s respectively.

The 5-site run used deterministic rows `S0001`, `S0002`, `S0028`, `S0031`, and
`S0050`; all five rows and unique IDs validated before the 40-site run began.
The 40-site output contains exactly 40 unique pilot IDs. Copernicus had 1
cache hit/4 misses in the gate and 5 hits/35 misses in the full run. Earth
Engine made 5 and 40 point requests; MERIT rasters were never exported or
downloaded.

`S0001` is a marine point whose public Copernicus tile returned HTTP 404. The
runner records this as `source_unavailable_nodata` and stores an explicit
all-nodata fixture; it never converts missing ocean data to elevation zero.
Marine and marine-freshwater catchment statuses remain policy-dependent, and
freshwater catchment delineation remains unimplemented.

Machine-readable outputs:

- `data/cache/staged_pilot/stage_5_sites.json`
- `data/cache/staged_pilot/stage_40_sites.json`

Reusable runner: `scripts/run_staged_pilot.py`. It logs stable per-site and
per-source timings and persists wall time, CPU time, Python allocation peak,
optional RSS, cache counts, and Earth Engine timing definition.
