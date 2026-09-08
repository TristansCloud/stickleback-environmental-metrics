# Pilot DEM/hydrology recommendation

## Provisional first-pass decision (40-site pilot)

The investigator has accepted Copernicus DEM GLO-30 as the first-pass local
topography source, including its DSM representation, and MERIT Hydro as the
first-pass hydrologic-context source. This is a provisional source selection
for script creation and the existing 40-site pilot only; it does not authorize
acquisition for the 599-site source dataset.

For the 40-site pilot, use a hybrid cache-first design: Copernicus DEM GLO-30
for local elevation/slope/relief and MERIT Hydro for flow direction,
accumulation, and any future catchment delineation.  Remote COG/range reads are
an acquisition method; each exact tile/window used is retained locally with a
JSON provenance sidecar.  A cache miss fails offline and does not silently
expand beyond the pilot.

For MERIT Hydro specifically, the first-pass acquisition method is Earth
Engine server-side sampling of `MERIT/Hydro/v1_0_1`, followed by local caching
of the small 40-site export table. This avoids downloading the approximately
195 GB global distribution. Earth Engine requires a Google account and a
registered Google Cloud project with the Earth Engine API enabled; see the
access details in [access_readiness_2026-09-07.md](access_readiness_2026-09-07.md).
The Earth Engine export is a derived cache, not a full offline source, so its
provenance records the asset ID/version, coordinates, bands, scale/projection,
sampling rule, task ID, timestamps, script/config hash, export destination,
local path, and checksum. A future fully offline fallback may retrieve only
the official 5° tiles or 30° packages intersecting the pilot, subject to the
provider's download access and licensing; it must remain an intentional,
checksum-verified pilot-only acquisition.

The practical alternative is a single DEM (for example Copernicus alone) with
local flow-routing.  It is simpler, but its DSM artifacts and inconsistent
hydrologic conditioning make it a weaker basis for catchments.  The hybrid
option is therefore recommended. The source selection can be revisited after
the first pilot outputs are available.

Future source-comparison requirement:

* Repeat the pilot extraction with an exchangeable DEM/hydrology source (for
  example, a bare-earth DEM or another hydrologically conditioned product) and
  compare coverage, nodata, elevation, slope/relief, and hydrologic outputs.
  Keep the source, version, CRS, vertical datum, resolution, retrieval date,
  checksum, and cached path in provenance so this comparison is reproducible.

Remaining scientific choices requiring investigator confirmation:

* For the first pass, the DSM is accepted. A later comparison should still
  quantify the effect of DSM versus bare-earth terrain if that distinction
  matters for interpretation.
* Confirm the vertical datum/height convention to use when combining providers;
  the pipeline records, but does not silently transform, vertical datums.
* Define catchments for marine and marine-freshwater samples (not applicable,
  adjacent terrestrial watershed, or a coastal drainage policy). The code keeps
  these values explicit: marine returns `not_applicable_marine`, while
  marine-freshwater returns `coastal_policy_required` until chosen.
