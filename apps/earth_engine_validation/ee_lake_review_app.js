/** Frozen lake candidate QC viewer. No live lookups, calculations, or writes.
 * Upload the three collections from ONE immutable lake-review bundle first.
 * Set ROOT to that private release's Earth Engine asset folder.
 */
var ROOT = 'projects/stickleback-507923/assets/stickleback_validation/ee_lake_review_v1_3c2c0cdae927cca6';
if (ROOT.indexOf('REPLACE_WITH_') !== -1) {
  throw new Error('Configure ROOT with the uploaded immutable lake-review release.');
}
var sites = ee.FeatureCollection(ROOT + '/lake_sites');
var selected = ee.FeatureCollection(ROOT + '/selected_candidates');
var evaluated = ee.FeatureCollection(ROOT + '/evaluated_polygons');
var map = ui.Map();
map.setOptions('SATELLITE');
var selector = ui.Select({placeholder: 'Choose lake study site'});
var status = ui.Label('Loading frozen lake sites…');
var details = ui.Panel();
var habitat = ui.Select({items: ['unreviewed', 'lake', 'reservoir', 'pond', 'other water', 'uncertain'],
  value: 'unreviewed'});
var identity = ui.Select({items: ['unreviewed', 'correct habitat', 'wrong habitat', 'uncertain'],
  value: 'unreviewed'});
var border = ui.Select({items: ['unreviewed', 'separate', 'shared border', 'connected water', 'uncertain'],
  value: 'unreviewed'});
var note = ui.Textbox({placeholder: 'Shoreline, islands, identity and neighbour notes',
  style: {stretch: 'horizontal'}});
var output = ui.Textbox({style: {stretch: 'horizontal'}});
var current = null;
var generation = 0;

function showProperties(title, properties) {
  details.add(ui.Label(title, {fontWeight: 'bold', margin: '12px 0 4px 0'}));
  Object.keys(properties || {}).sort().forEach(function(key) {
    details.add(ui.Label(key + ': ' + String(properties[key]),
      {fontSize: '11px', whiteSpace: 'pre-wrap'}));
  });
}

function selectSite(id) {
  if (!id) return;
  var token = ++generation;
  current = null;
  details.clear();
  habitat.setValue('unreviewed'); identity.setValue('unreviewed'); border.setValue('unreviewed');
  note.setValue(''); output.setValue('');
  status.setValue('Loading ' + id + '…');
  var point = sites.filter(ee.Filter.eq('sample_id', id));
  var chosen = selected.filter(ee.Filter.eq('sample_id', id));
  var neighbours = evaluated.filter(ee.Filter.eq('sample_id', id))
    .filter(ee.Filter.eq('selected_candidate', false));
  map.layers().set(1, ui.Map.Layer(neighbours.style({color: 'ff9900', fillColor: 'ff990022', width: 2}), {},
    'Other evaluated polygons (including rejected)'));
  map.layers().set(2, ui.Map.Layer(chosen.style({color: '00ffff', fillColor: '00ffff22', width: 3}), {},
    'Selected candidate — requires QC'));
  map.layers().set(3, ui.Map.Layer(point.style({color: 'ff00ff', pointSize: 7}), {}, 'Original coordinate'));
  map.centerObject(point, 13);
  point.first().evaluate(function(value, error) {
    if (token !== generation) return;
    if (error || !value) { status.setValue('Cannot load site: ' + (error || id)); return; }
    current = value.properties;
    showProperties('Original site and lookup evidence', current);
    evaluated.filter(ee.Filter.eq('sample_id', id)).evaluate(function(collection, polygonError) {
      if (token !== generation) return;
      if (polygonError) { status.setValue('Cannot load polygon evidence: ' + polygonError); return; }
      var features = collection ? collection.features : [];
      features.forEach(function(feature) {
        var props = feature.properties;
        showProperties((props.selected_candidate ? 'Selected: ' : 'Other: ') +
          props.osm_type + '/' + props.osm_id, props);
        details.add(ui.Label('Open OSM object', {},
          'https://www.openstreetmap.org/' + props.osm_type + '/' + props.osm_id));
      });
      status.setValue(id + ': ' + current.status + '; ' + features.length +
        ' evaluated polygons. Discovered objects without retrieved geometry appear in discovery_evidence.');
    });
  });
}
selector.onChange(selectSite);
var copyReview = ui.Button('Prepare review record for copying', function() {
  if (!current) { output.setValue('Wait for a site to load.'); return; }
  output.setValue(JSON.stringify({sample_id: current.sample_id, app_release_id: current.app_release_id,
    selected_osm_type: current.osm_type, selected_osm_id: current.osm_id,
    habitat: habitat.getValue(), identity: identity.getValue(), neighbour_relationship: border.getValue(),
    note: note.getValue(), reviewed_at_utc: new Date().toISOString(),
    notice: 'Browser memory only. Copy this record to preserve it.'}));
});
var panel = ui.Panel({style: {width: '440px', padding: '8px'}});
panel.add(ui.Label('Lake polygon verification', {fontSize: '18px', fontWeight: 'bold'}));
panel.add(ui.Label('Inspect original coordinates, candidate identity, shorelines, islands and neighbouring water. '
  + 'Containment alone does not establish a lake. Satellite imagery can differ in date from OSM.',
  {whiteSpace: 'pre-wrap'}));
panel.add(selector); panel.add(status); panel.add(details);
panel.add(ui.Label('Manual habitat classification')); panel.add(habitat);
panel.add(ui.Label('Candidate identity')); panel.add(identity);
panel.add(ui.Label('Neighbour relationship (describe object IDs in notes)')); panel.add(border);
panel.add(note); panel.add(copyReview); panel.add(output);
panel.add(ui.Label('Review text is not saved. Switching sites clears it; copy it first.',
  {whiteSpace: 'pre-wrap'}));
map.addLayer(sites.style({color: 'e31a1c', pointSize: 4}), {}, 'All original lake-study coordinates');
map.addLayer(ee.FeatureCollection([]), {}, 'Other evaluated polygons');
map.addLayer(ee.FeatureCollection([]), {}, 'Selected candidate');
map.addLayer(ee.FeatureCollection([]), {}, 'Original coordinate');
map.setCenter(0, 45, 2);
ui.root.clear(); ui.root.add(ui.SplitPanel({firstPanel: panel, secondPanel: map, wipe: false}));
sites.aggregate_array('sample_id').evaluate(function(ids, error) {
  if (error || !ids) { status.setValue('Cannot load lake review assets: ' + error); return; }
  selector.items().reset(ids.sort());
  status.setValue(ids.length + ' sites loaded. All results require manual verification.');
});
