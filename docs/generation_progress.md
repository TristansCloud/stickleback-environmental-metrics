# Full dataset generation progress

Scope: all 599 original sites, retaining stable IDs and original ecotype.
All inferred classes remain provisional. Marine-specific metrics stay empty.
External coordinate lookups are authorized by the user.

## Steps

1. Verify public point elevation/climate access on a small cohort; keep source
   metadata, units, climate period and missingness explicit.
2. Complete/test river vector snapping and separate MERIT cell alignment.
3. Exercise point/lake/river workflows on the existing test cohorts; inspect
   errors and stop repeatedly failing remote paths rather than broadening them.
4. Generate the full review table from available point data and verified caches;
   expand successful remote paths only after pilot checks.
5. Add exploratory shoreline-buffer relative elevation where complete lake
   geometry and terrain inputs exist. Do not infer lake depth without the thesis
   equation and variable-buffer rule.
6. Save the review bundle, tests, source provenance, error/coverage summary, and
   reproducible laptop commands. Expert corrections must remain separate from
   immutable source data. Report incomplete metrics honestly.

## Starting state

The previous river implementation was interrupted before testing when automatic
review rejected a public coordinate lookup. The user has since explicitly
authorized sending coordinates out and resuming work. The environment has no
Earth Engine project configuration or credentials. Existing frozen point-pilot
and lake outputs are examined before acquiring replacements.

## Completed snapshot (2026-11-01)

| Step | Result |
| --- | --- |
| Point pilot | 26/26 elevations and climate responses succeeded |
| Full point collection | 599/599 elevations and climate values; 229 nominal climate cells; no retrieval errors in the completed run |
| Lake geometry | 24 known OSM candidates revalidated; 88 HydroLAKES containing candidates; 98 distinct sites after preferring known OSM geometry |
| River pilot and expansion | Four provisional core pilot reach matches; full 61-site inferred-stream cohort produced 36 provisional reach upstream-area attributes |
| Shoreline exploration | 98 attempted locally; 91 exploratory profiles, six unstable/insufficient proxies, one geometry beyond the method's extent |
| Reproduction | Complete workflow reproduced from caches with network disabled |
| Verification | 93 tests pass; original 599 IDs, coordinates, and ecotypes preserved; raw geofiles excluded from Git |

## Explicit remaining scientific gaps

- New sample-cell MERIT accumulation remains unavailable: local MERIT rasters
  and Earth Engine configuration/credentials are absent. River reach-outlet
  area is supplied in a separate column, never substituted for that value.
- 115 inferred-lake sites lack a containing polygon in the selected local/known
  sources. HydroLAKES's 10 ha threshold omits smaller waterbodies; no points
  were moved to force matches. Unreliable Overpass discovery was not expanded.
- Shoreline perimeter normalization is pending. DSM-relative shoreline profiles
  are exploratory, not depth or slope measurements. Thesis equation, buffer
  rule, and lake surface elevation definition remain required.
- All inferred classes need expert review. The review bundle includes blank
  correction fields and a prioritized classification sheet for Marius.
- Marine-specific metrics remain blank by request.

The finished portable bundle contains the full CSV, review queue, original
source, data dictionary, source provenance, coverage, and relevant vector
subsets. Bulk archives and raster caches are local only, with reproducible source
URLs and checksums; a home server can retain them for durable reuse later.
