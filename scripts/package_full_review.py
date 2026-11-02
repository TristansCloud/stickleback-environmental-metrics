"""Validate and package the review table; raw archives/rasters stay outside Git."""

from __future__ import annotations
import argparse, csv, hashlib, json, shutil, zipfile
from pathlib import Path
from enviro_data.input import load_sites

ROOT = Path(__file__).resolve().parents[1]


def package(bundle, *, code_ref="working-tree"):
    bundle = Path(bundle)
    summary = json.loads((bundle / "coverage_summary.json").read_text())
    table = bundle / "stickleback_full_review_v1.csv"
    with table.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    source = load_sites(ROOT / "site_overview_v1_clean.csv", strict=True).records
    assert len(rows) == len(source) == 599
    expected = {r.sample_id: r for r in source}
    assert len({r["sample_id"] for r in rows}) == 599
    for row in rows:
        r = expected[row["sample_id"]]
        assert (float(row["latitude"]), float(row["longitude"])) == (
            r.latitude,
            r.longitude,
        )
        assert row["source_ecotype"] == r.ecotype
        assert row["reviewed_waterbody_class"] == ""
        assert (
            row["lake_depth_estimate_m"] == ""
            and row["shoreline_slope_degrees"] == ""
            and row["marine_specific_metrics"] == ""
        )
        if row["lake_area_m2"]:
            assert float(row["lake_area_m2"]) > 0 and float(row["lake_perimeter_m"]) > 0
        if row["river_reach_upstream_area_km2"]:
            assert float(row["river_reach_upstream_area_km2"]) >= 0
    shutil.copy2(ROOT / "site_overview_v1_clean.csv", bundle / "original_sites.csv")
    for src, name in [
        (
            ROOT / "data/cache/combined_lakes/lake_polygons.geojson",
            "lake_candidates.geojson",
        ),
        (
            ROOT / "data/cache/river_hydrorivers_full/river_pilot.geojson",
            "river_candidates.geojson",
        ),
        (ROOT / "data/cache/hydrorivers/sources.json", "hydrorivers_sources.json"),
        (ROOT / "data/cache/hydrolakes/provenance.json", "hydrolakes_source.json"),
    ]:
        shutil.copy2(src, bundle / name)

    def priority(row):
        if row["working_waterbody_type"] == "unknown":
            return 1
        if (
            row["manual_review"] == "True"
            or row["lake_name_evidence"] == "name_differs"
        ):
            return 2
        return 3

    fields = [
        "review_priority",
        "sample_id",
        "population_name",
        "latitude",
        "longitude",
        "source_ecotype",
        "working_waterbody_type",
        "name_inferred_waterbody_type",
        "matched_terms",
        "working_type_basis",
        "lake_name_evidence",
        "reviewed_waterbody_class",
        "reviewed_waterbody_name",
        "reviewed_latitude",
        "reviewed_longitude",
        "reviewer",
        "review_notes",
    ]
    with (bundle / "review_queue.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        w.writeheader()
        for row in sorted(rows, key=lambda r: (priority(r), r["sample_id"])):
            w.writerow({**row, "review_priority": priority(row)})
    definitions = {
        "sample_id": "Stable original sample ID; join expert corrections by this field.",
        "source_ecotype": "Original supplied ecotype; may reflect population biology rather than collection waterbody.",
        "working_waterbody_type": "Provisional class inferred from name and original ecotype, not expert-confirmed.",
        "name_inference_confidence": "Lexical heuristic confidence, not independently calibrated habitat certainty.",
        "manual_review": "Original inference conflict flag; every site still requires review even if this is False.",
        "point_elevation_m": "Original-coordinate Copernicus GLO-90 2021 DSM elevation in metres; not water level or bathymetry.",
        "annual_mean_precipitation_mm_day": "Annual climatological mean daily precipitation rate, mm/day; not annual precipitation total.",
        "mean_annual_air_temperature_c": "Mean annual 2 m air temperature in degrees Celsius, NASA POWER climatology.",
        "climate_period": "Exact provider-returned baseline; this release is January 2001–December 2025.",
        "climate_grid_latitude": "Nominal MERRA-2 grid centre latitude, not corrected sample latitude.",
        "climate_grid_longitude": "Nominal MERRA-2 grid centre longitude, not corrected sample longitude.",
        "climate_query_latitude": "Latitude actually sent for this cached climate response; original point or shared cell centre.",
        "climate_query_longitude": "Longitude actually sent for this cached climate response; original point or shared cell centre.",
        "lake_area_m2": "Whole candidate polygon surface area in square metres; islands subtracted.",
        "lake_perimeter_m": "Whole candidate shoreline length in metres, including island shores; raw geometry resolution.",
        "lake_area_perimeter_m": "Area/perimeter ratio A/P, unit metres.",
        "lake_shoreline_development": "Dimensionless shoreline development P/(2*sqrt(pi*A)); distinct from A/P.",
        "lake_hylak_id": "HydroLAKES identifier when this source supplies the candidate; not an OSM ID.",
        "lake_geometry_resolution_status": "Raw source resolution is retained; shoreline normalization is pending.",
        "river_reach_upstream_area_km2": "HydroRIVERS total contributing area at reach outlet, km²; not exact sample-point accumulation.",
        "river_reach_strahler_order": "HydroRIVERS Strahler stream order for the provisional matched reach.",
        "river_reach_average_discharge_m3_s": "HydroRIVERS estimated long-term mean reach discharge, m³/s; not measured discharge.",
        "river_snap_distance_m": "Approximate local-plane original-point to provisional stream-vector distance, metres.",
        "river_flow_connection_verified": "False: topology/flow connection to original sample has not been independently verified.",
        "river_merit_alignment_status": "Separate MERIT native-grid channel alignment status; local MERIT/EE inputs were unavailable in this run.",
        "lake_surface_dem_proxy_m": "Median interior DSM sample elevation; exploratory proxy, not a measured lake water level.",
        "lake_surface_dem_range_m": "Range among valid lake-interior DSM sample elevations, metres; >5 m withholds relative metrics.",
        "lake_depth_estimate_m": "Blank: thesis equation and variable-buffer rule have not been supplied.",
        "shoreline_slope_degrees": "Blank: deferred; buffered relative elevation is not shoreline slope.",
        "marine_specific_metrics": "Blank by design; generic point elevation/climate remain available.",
    }
    with (bundle / "data_dictionary.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["column", "description"])
        for field in rows[0]:
            text = definitions.get(field)
            if text is None:
                if field.startswith("cached_point_"):
                    text = "Historical frozen original-point pilot value/status; not a new channel snap or catchment result."
                elif field.startswith("shore_"):
                    text = "Exploratory statistic for external disjoint bands ending at 50, 100 or 250 m. Relative elevations are metres above interior DSM proxy; counts are sample points, not independent pixels."
                elif field.startswith("river_snapped_"):
                    text = "MERIT value at a supported native channel cell; blank until alignment succeeds."
                elif field.startswith("air_temperature_"):
                    text = "Monthly climatological 2 m air temperature in degrees Celsius; regional atmospheric context."
                elif field.startswith("precipitation_"):
                    text = "Monthly climatological mean daily precipitation in mm/day; not a monthly total."
                elif field.startswith("reviewed_") or field in {
                    "reviewer",
                    "review_notes",
                }:
                    text = "Blank expert-review field; retain original and inferred evidence separately."
                elif field.endswith("_source_key"):
                    text = "Join to point_sources entries in source_provenance.json for source, query, units and checksums."
                elif field.endswith("_status"):
                    text = "Availability/QA/applicability status; blank numeric values are never substituted with zero."
                else:
                    text = "Evidence, identifier or provenance field; see README and source_provenance.json."
            w.writerow([field, text])
    readme = f"""# Stickleback environmental review bundle — 2026-11-01

This is a review snapshot for the **entire original 599-site input**. Original
coordinates, IDs and ecotypes are preserved. Inferred lake/stream/marine/transition
classes remain hypotheses. No new expert-confirmed waterbody labels are claimed.

## Coverage

| Family | Available |
| --- | ---: |
| Original sites | 599 |
| Original-point DEM elevation | {summary['point_elevation'].get('ok',0)} |
| Monthly/annual atmospheric climate | {summary['climate'].get('ok',0)} |
| Containing lake polygon candidates | {summary['lake_polygons']} |
| River reach upstream-area candidates | {summary['river_reach_upstream_areas']} |
| Supported sample-cell MERIT accumulation | {summary['river_snapped_merit_areas']} |
| Exploratory shoreline elevation profiles | {summary['shoreline_profiles'].get('exploratory',0)} |

The 599 sites share {summary.get('climate_unique_nominal_grid_cells')} nominal
MERRA-2 climate cells. These are not 599 independent fine-resolution climate
measurements. Climate baseline is **January 2001–December 2025**. Temperature is
2 m **air** temperature (°C); precipitation is a **mean daily rate (mm/day)**.

## Start here

- `stickleback_full_review_v1.csv`: full site table, UTF-8 with BOM for Excel.
- `review_queue.csv`: smaller classification/correction sheet, prioritized for
  unknown classes and conflicting evidence. Every row still needs review.
- `original_sites.csv`: unchanged six-column original input.
- `data_dictionary.csv`: column meanings, units and caveats.
- `coverage_summary.json`: exact availability counts and hashes.
- `source_provenance.json`: source responses, periods, versions, geometry and
  terrain provenance. Cache paths identify generation files, not portable URLs.
- `sample_points.geojson`, `lake_candidates.geojson`, `river_candidates.geojson`:
  GIS review layers in WGS84 longitude/latitude.

For expert review, fill `reviewed_waterbody_class` (lake, river/stream, marine,
estuary/brackish, or unknown), reviewed waterbody name, corrected coordinates
where needed, reviewer and notes. Use `sample_id` to join corrections. Do not
replace the original coordinate/ecotype columns or interpret inferred confidence
as ground truth. Unknown remains an acceptable class.

## Interpretation limits

Point elevation is Copernicus GLO-90 **DSM**, not bathymetry or measured lake
surface elevation. Ocean/shore zero values must not be interpreted as water depth.
The `cached_point_*` columns preserve earlier pilot results separately.

Lake candidates combine known OSM objects and HydroLAKES v1.0. The original
point must fall in or on the polygon; points were not moved to force a lake match.
HydroLAKES covers lakes of at least **10 ha**, so small-lake omissions are expected.
All candidate identities, unnamed features and mismatched names need review.
Area is spherical WGS84 with islands subtracted. Perimeter includes island
shores at **raw source geometry resolution**, without shoreline normalization.
Area/perimeter (metres) and shoreline development (dimensionless) are different
columns. Cross-source perimeter differences may reflect geometry resolution.

River reach upstream area is measured at the **reach outlet**, not the original
sample point. HydroRIVERS stream order/discharge are model/source attributes.
The sample-point MERIT raster alignment adapter is implemented but those new
values are unavailable here because local MERIT rasters/EE credentials were
absent. Ambiguous reaches and classification challenges were not forced.

Shoreline profiles use locally cached Copernicus GLO-90 tiles and disjoint
land-side bands 0–50, 50–100, and 100–250 m, including islands. The interior DSM
median is only a provisional lake-surface proxy. The 50 m band is below nominal
source resolution. Sample coordinates are not independent raster pixels.
Surface proxies with insufficient interior coverage or >5 m spread are withheld;
large geometry beyond the local method is unsupported. These are **not lake
 depth estimates or shoreline slopes**. The thesis equation and variable-buffer
rule are still needed. Marine-specific fields remain blank by design.

## Reproduction and attribution

Code reference: `{code_ref}`. Recipe: `docs/full_review_workflow.md` in the repo.
Raw global/regional archives and GeoTIFFs are cached locally and excluded from
Git. This bundle includes only the review results and relevant vector subsets.

Sources: NASA POWER/MERRA-2; Copernicus DEM GLO-90 2021 via Open-Meteo and public
AWS tiles; HydroLAKES (Messager et al. 2016, CC BY 4.0); HydroRIVERS (Lehner &
Grill 2013, HydroSHEDS); and © OpenStreetMap contributors (ODbL). Source URLs and
checksums are retained in provenance and source files. Retain these attributions
when sharing the review data. Cached MERIT pilot context is from MERIT Hydro
(Yamazaki et al. 2019).
"""
    (bundle / "README.md").write_text(
        readme.replace("\n depth estimates", "\ndepth estimates")
    )
    manifest = {
        "code_ref": code_ref,
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(bundle.iterdir())
            if p.is_file() and p.name != "bundle_manifest.json"
        },
    }
    (bundle / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    output = bundle.parent / "stickleback_review_2026-11-01.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(bundle.iterdir()):
            if p.is_file():
                z.write(p, p.name)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
    return {
        "zip": str(output),
        "bytes": output.stat().st_size,
        "files": len(manifest["files"]) + 1,
        "rows": len(rows),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bundle", type=Path, default=ROOT / "data/cache/full_review_bundle"
    )
    p.add_argument("--code-ref", default="working-tree")
    a = p.parse_args()
    print(json.dumps(package(a.bundle, code_ref=a.code_ref), indent=2))
