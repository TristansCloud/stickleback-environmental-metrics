from __future__ import annotations

from pathlib import Path


def test_validation_viewer_is_a_frozen_read_only_template() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "apps" / "ee_pilot_validation_app.js").read_text(encoding="utf-8")

    assert source.count("REPLACE_WITH_") >= 3
    assert "ee.FeatureCollection(ASSETS.pilotOutput)" in source
    assert "ee.FeatureCollection(ASSETS.osmMatches)" in source
    assert "ee.FeatureCollection(ASSETS.copernicusWindows)" in source
    assert "Prepare review record for copying" in source
    assert "not saved or submitted by this app" in source

    forbidden = ("Export.", "ee.Image(", "reduceRegion", "getDownloadURL", "fetch(")
    assert all(token not in source for token in forbidden)
