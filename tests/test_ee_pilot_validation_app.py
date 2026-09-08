from __future__ import annotations

from pathlib import Path


def test_validation_viewer_is_a_frozen_read_only_template() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "apps" / "earth_engine_validation" / "ee_pilot_validation_app.js").read_text(encoding="utf-8")

    assert source.count("REPLACE_WITH_") >= 3
    assert "ee.FeatureCollection(ASSETS.pilotOutput)" in source
    assert "ee.FeatureCollection(ASSETS.osmMatches)" in source
    assert "ee.FeatureCollection(ASSETS.copernicusWindows)" in source
    assert "Prepare review record for copying" in source
    assert "not saved or submitted by this app" in source

    forbidden = ("Export.", "ee.Image(", "reduceRegion", "getDownloadURL", "fetch(")
    assert all(token not in source for token in forbidden)


def test_v3_viewer_copy_changes_only_the_asset_constants() -> None:
    root = Path(__file__).resolve().parents[1]
    template = (root / "apps" / "earth_engine_validation" / "ee_pilot_validation_app.js").read_text(encoding="utf-8")
    app_ready = (root / "apps" / "earth_engine_validation" / "ee_pilot_validation_app_v3.js").read_text(encoding="utf-8")
    required_base = (
        "projects/stickleback-507923/assets/stickleback_validation/"
        "ee_app_validation_assets_v3_4e20cbe056b676f2/"
    )

    def without_assets(source: str) -> str:
        start = source.index("var ASSETS = Object.freeze({")
        end = source.index("\n});", start) + len("\n});")
        return source[:start] + "<ASSETS>" + source[end:]

    assert without_assets(template).rstrip() == without_assets(app_ready).rstrip()
    asset_literals = app_ready.replace("' +\n      '", "")
    assert required_base + "pilot_output" in asset_literals
    assert required_base + "osm_matches" in asset_literals
    assert required_base + "copernicus_windows" in asset_literals
    asset_block = app_ready[
        app_ready.index("var ASSETS = Object.freeze({") : app_ready.index("\n});")
    ]
    assert "REPLACE_WITH_" not in asset_block


def test_current_viewer_uses_a_stable_registry_for_three_release_assets() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "apps" / "earth_engine_validation" / "ee_pilot_validation_app_current.js").read_text(encoding="utf-8")
    registry_id = (
        "projects/stickleback-507923/assets/stickleback_validation/app_current/"
        "validation_app_registry_current"
    )

    asset_block = source[source.index("var ASSETS = {") : source.index("\n};")]
    normalized = asset_block.replace("' +\n      '", "")
    assert normalized.count(registry_id) == 1
    assert "ee.FeatureCollection(ASSETS.registry)" in source
    for property_name in (
        "pilot_output_asset_id",
        "osm_matches_asset_id",
        "copernicus_windows_asset_id",
    ):
        assert property_name in source
    assert "var ASSETS = Object.freeze" not in source
    assert "Object.assign(" not in source
    assert "mergedProperties(registryProperties," in source
    assert "app_release_id: prop(registryProperties, 'app_release_id')" in source
    assert "Additional stored properties" in source
    assert "['Population name', 'population_name']" in source
    assert "['Population abbreviation', 'population_abbreviation']" in source
    assert source.count("ui.Textbox(") == 3
    assert "ui.Textarea(" not in source
    assert "var status =" not in source
    assert "var statusLabel = ui.Label(" in source
    assert "browser memory only" in source
    assert "Copyable review record appears here." in source
    assert "reviewer_name: reviewerName.getValue()" in source
    assert "review_created_at_utc: new Date().toISOString()" in source
    assert "['Catchment delineation status', 'hydrology_status']" in source
    assert "['Catchment delineation note', 'hydrology_message']" in source
    assert "heading('OSM match')" in source
    assert "heading('MERIT Hydro point values')" in source
    assert "Frozen OSM match" not in source
    assert "Stored MERIT Hydro point values" not in source
    for label in (
        'Elevation (elv, m)',
        'Flow direction (dir, D8 code)',
        'Upstream drainage area (upa, km²)',
        'Upstream drainage pixels (upg, count)',
        'Height above nearest drainage (hnd, m)',
        'Water-body mask (wat, categorical)',
        'River channel width (wth, m)',
        'Elevation (elv) data status',
        'River channel width (wth) data status',
    ):
        assert label in source
    assert "function suppressAdditionalProperty(key)" in source
    assert "function subheading(text)" in source
    for label in (
        "Site and environmental context",
        "Release and data integrity",
        "Match metrics",
        "Snapshot and data integrity",
        "Environmental metrics",
        "Window and data integrity",
        "Data quality and interpretation",
        "Runtime metrics",
        "Current-channel provenance",
    ):
        assert f"subheading({label!r})" in source
    for hidden_key in (
        "topography_provenance_path",
        "osm_failure_diagnostics",
        "'site_'",
        "'topography_'",
        "'merit_hydro_'",
        "'osm_'",
        "'registry_'",
        "'app_current_'",
    ):
        assert hidden_key in source
    forbidden = ("Export.", "ee.Image(", "reduceRegion", "getDownloadURL", "fetch(",
                 "Object.freeze(", "Object.assign(", "=>", "const ", "let ")
    assert all(token not in source for token in forbidden)
