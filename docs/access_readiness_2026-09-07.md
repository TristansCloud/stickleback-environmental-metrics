# Online access readiness (2026-09-07)

This note records a bounded, read-only access check for the existing 40-site
pilot. No account was created, no authentication was attempted, no raster was
downloaded, and no source CSV or code/configuration was changed.

## Findings

### Copernicus DEM GLO-30

There are two relevant access paths with different account requirements:

* The Copernicus Data Space (CDSE) STAC catalogue is publicly discoverable.
  The collection endpoint returned HTTP 200 JSON and advertises global extent
  and the `CopDEM COG (30 m)` collection:
  <https://stac.dataspace.copernicus.eu/v1/collections/cop-dem-glo-30-dged-cog>.
* The public AWS Open Data mirror is usable without an AWS account. Its
  registry entry explicitly states “Access (No AWS account required)” and
  provides the `copernicus-dem-30m` bucket:
  <https://registry.opendata.aws/copernicus-dem/>. A bounded S3 ListObjects
  request returned HTTP 200 XML with one key, and the bucket readme returned
  HTTP 200. This is the most practical first-pass route for exact public COG
  tile reads, subject to checking the public-tile list for each pilot site.
* CDSE account registration is still required for CDSE-managed GLO-30 access
  paths. The current CDSE documentation marks `COPERNICUS_30` as requiring
  CCM registration, and CDSE bulk OData/S3 access requires a registered
  account/OAuth or generated credentials:
  <https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM.html>
  and <https://documentation.dataspace.copernicus.eu/APIs/S3.html>.

Therefore, no account is needed if the AWS public mirror is selected and its
public coverage is sufficient; a CDSE account is needed if the implementation
uses CDSE authenticated download/bulk access or the Sentinel Hub DEM service.

### Recommended pilot access path: Earth Engine

Because the investigator has the MERIT download password but does not want to
store the approximately 195 GB global package locally, the first-pass plan is
to use the public Earth Engine catalog asset as a server-side source:

```text
MERIT/Hydro/v1_0_1
```

The local pilot workflow should authenticate with the investigator's Google
account, initialize a registered Google Cloud project, and issue one bounded
request for the deterministic 40-site pilot points. Earth Engine requires a
Cloud project with the Earth Engine API enabled and registration for either
noncommercial or commercial use. For a noncommercial research project, the
project still needs the noncommercial eligibility questionnaire/verification;
a billing account is not required for unpaid access. A service account is not
needed for an interactive local test and should be deferred until unattended
runs are required. See <https://developers.google.com/earth-engine/guides/access>
and <https://developers.google.com/earth-engine/guides/auth>.

### Local configuration bootstrap

Use `config/earth_engine.toml.example` as the checked-in template and copy it
to the ignored `config/earth_engine.toml`. The local copy records the project
ID `stickleback-507923`, the `MERIT/Hydro/v1_0_1` asset, and the 40-site bounds.
Authentication remains outside project configuration: OAuth credentials,
service-account keys, passwords, and tokens must stay in the local Earth
Engine credential store and must never be written to TOML or committed.

For this pilot, sample only the required bands at the site coordinates and
export a small table rather than raster tiles. Candidate bands are `elv`,
`dir`, `upa`, `upg`, `hnd`, and, if needed, `wth`/`wat`. Preserve documented
ocean/no-data sentinels as null; never coerce them to zero elevation. See
<https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1>.

The exported table is a derived pilot cache, not a complete offline copy of
MERIT Hydro. Its provenance must include the catalog asset ID/version, exact
pilot coordinates, selected bands, sampling scale/projection, reducer or
resampling rule, request/script/config hash, Earth Engine task ID, submission
and completion timestamps, export destination, local path, and checksum. The
cache can then be reused offline for the 40-site run. Recreating it later
still depends on Earth Engine retaining the catalog asset and on valid account
and project access.

The official download remains a future offline fallback. MERIT Hydro is
organized as 5° × 5° GeoTIFF tiles bundled into 30° × 30° archives, so a later
approved fallback can intentionally retrieve only packages intersecting the
pilot sites, checksum them, and record source URL, version, tile/package name,
CRS, vertical datum, resolution, retrieval date, and local path. The first
pass must not download the global package or use the password in the
repository. See <https://global-hydrodynamics.github.io/MERIT_Hydro/>.

### MERIT Hydro

The official MERIT Hydro v1.0.1 page is publicly viewable (HTTP 200), but its
download instructions require completing a Google registration/license form
and receiving a password by email:
<https://global-hydrodynamics.github.io/MERIT_Hydro/>. The original 3-arcsec
MERIT Hydro GeoTIFF/tar downloads therefore require registration/password
access; no public unauthenticated COG endpoint was identified. The Google
Earth Engine catalogue page is public (HTTP 200), but using the Earth Engine
API requires Google/Earth Engine authentication and a Cloud project:
<https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1>
and <https://developers.google.com/earth-engine/guides/auth>.

## Exact bounded tests

All requests used `Invoke-WebRequest`, a 20-second timeout, a descriptive
user-agent, and metadata/page responses only:

* `GET https://stac.dataspace.copernicus.eu/v1/` -> HTTP 200,
  `application/json`, 3,670 bytes.
* `GET https://stac.dataspace.copernicus.eu/v1/collections/cop-dem-glo-30-dged-cog`
  -> HTTP 200, `application/json`, 3,927 bytes.
* `GET https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=contains(Name,%27COP-DEM_GLO-30%27)&$top=1`
  -> HTTP 200, 50-byte JSON response (catalogue reachable; no product body
  was downloaded).
* `GET https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/?list-type=2&max-keys=1`
  -> HTTP 200, 750-byte XML response (one-key listing only).
* `GET https://copernicus-dem-30m.s3.amazonaws.com/readme.html` -> HTTP 200,
  8,536 bytes.
* `GET https://global-hydrodynamics.github.io/MERIT_Hydro/` -> HTTP 200,
  20,989-byte HTML page.
* `GET https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1`
  -> HTTP 200, 98,760-byte HTML page.

## Next safe test

After deciding whether to use the public AWS mirror, perform a bounded,
pilot-only STAC/object metadata check for the exact tile keys covering the 40
sites (HEAD or range request, no full object download), then cache only the
required windows. MERIT Hydro acquisition should wait for the investigator's
registration decision, or use an explicitly approved alternative distribution;
do not place credentials in the repository.
