import csv
import hashlib
import json
from pathlib import Path

import pytest

from enviro_data.ee_full_review import prepare_full_review


def write_csv(path, rows):
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def refresh_manifest(path):
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()
             if p.name != 'bundle_manifest.json'}
    (path / 'bundle_manifest.json').write_text(json.dumps({'files': files, 'code_ref': 'fixture'}))


def source_bundle(path):
    path.mkdir()
    original = [{'sample_id': 'S1', 'Longitude': '1', 'Latitude': '2', 'Ecotype': 'freshwater'},
                {'sample_id': 'S2', 'Longitude': '3', 'Latitude': '4', 'Ecotype': 'marine'}]
    write_csv(path / 'original_sites.csv', original)
    review = [{'sample_id': r['sample_id'], 'longitude': r['Longitude'], 'latitude': r['Latitude'],
               'source_ecotype': r['Ecotype'], 'population_name': '001', 'lake_osm_id': '007',
               'point_elevation_m': '0', 'lake_depth_estimate_m': '', 'lake_area_m2': '',
               'river_reach_upstream_area_km2': '', 'shoreline_elevation_status': 'unavailable',
               'review_required': 'True'} for r in original]
    write_csv(path / 'stickleback_full_review_v1.csv', review)
    points = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [float(r['Longitude']), float(r['Latitude'])]},
               'properties': {'sample_id': r['sample_id']}} for r in original]
    (path / 'sample_points.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': points}))
    for name in ['lake_candidates', 'river_candidates']:
        (path / (name + '.geojson')).write_text(json.dumps({'type': 'FeatureCollection', 'features': []}))
    # Deliberately non-alphabetic order to verify elevation-to-coordinate pairing.
    provenance = {'shoreline_results': {'S1': {'plan': {'groups': {'lake_surface': [[1, 2]],
                   'shore_50m': [[1.1, 2]], 'shore_100m': [[1.2, 2]]}},
                   'sample_elevations_m': [7, 8, None], 'status': 'exploratory'}}}
    (path / 'source_provenance.json').write_text(json.dumps(provenance))
    (path / 'coverage_summary.json').write_text('{}')
    (path / 'data_dictionary.csv').write_text('column,description\n')
    refresh_manifest(path)
    return path


def test_original_coordinates_null_zero_ids_and_sampling_pairing_survive(tmp_path):
    source = source_bundle(tmp_path / 'source')
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    output = prepare_full_review(source, tmp_path / 'output', expected_sites=2)
    sites = json.loads((output / 'sites.geojson').read_text())['features']
    props = sites[0]['properties']
    assert sites[0]['geometry']['coordinates'] == [1, 2]
    assert props['point_elevation_m'] == 0
    assert props['lake_depth_estimate_m'] is None
    assert props['population_name'] == '001' and props['lake_osm_id'] == '007'
    assert props['has_lake_polygon'] is False
    assert props['review_required'] is True
    samples = json.loads((output / 'shoreline_samples.geojson').read_text())['features']
    assert [(p['properties']['group'], p['properties']['elevation_m'], p['geometry']['coordinates'])
            for p in samples] == [('lake_surface', 7, [1, 2]), ('shore_50m', 8, [1.1, 2]), ('shore_100m', None, [1.2, 2])]
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}
    assert prepare_full_review(source, tmp_path / 'output', expected_sites=2) == output
    (output / 'sites.geojson').write_text('{}')
    with pytest.raises(ValueError, match='immutable'):
        prepare_full_review(source, tmp_path / 'output', expected_sites=2)


def test_rejects_tampering_changed_coordinates_duplicate_ids_and_nonfinite(tmp_path):
    source = source_bundle(tmp_path / 'source')
    table = source / 'stickleback_full_review_v1.csv'
    text = table.read_text()
    table.write_text(text.replace('freshwater', 'changed'))
    with pytest.raises(ValueError, match='checksum'):
        prepare_full_review(source, tmp_path / 'out', expected_sites=2)
    refresh_manifest(source)
    with pytest.raises(ValueError, match='Original coordinates/ecotype'):
        prepare_full_review(source, tmp_path / 'out', expected_sites=2)
    table.write_text(text.replace('S2', 'S1'))
    refresh_manifest(source)
    with pytest.raises(ValueError, match='unique'):
        prepare_full_review(source, tmp_path / 'out', expected_sites=2)
    table.write_text(text.replace(',0,', ',nan,'))
    refresh_manifest(source)
    with pytest.raises(ValueError, match='Non-finite'):
        prepare_full_review(source, tmp_path / 'out', expected_sites=2)


def test_incomplete_shoreline_evidence_is_rejected(tmp_path):
    source = source_bundle(tmp_path / 'source')
    p = source / 'source_provenance.json'
    data = json.loads(p.read_text())
    data['shoreline_results']['S1']['sample_elevations_m'].pop()
    p.write_text(json.dumps(data))
    refresh_manifest(source)
    with pytest.raises(ValueError, match='count mismatch'):
        prepare_full_review(source, tmp_path / 'out', expected_sites=2)
