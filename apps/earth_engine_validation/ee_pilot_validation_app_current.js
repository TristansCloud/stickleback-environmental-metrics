/**
 * Restricted validation viewer: stable-current release channel.
 *
 * This App reads one stable release registry. The registry names exactly three
 * immutable FeatureCollections for one approved release; no live source,
 * pipeline output, raster, or external service is queried here. Advancing the
 * channel replaces registry content, never this Code Editor source. See README.
 */
// The Code Editor uses a restricted JavaScript runtime: keep this plain ES5.
// This is configuration rather than a security boundary; the registry's
// provenance/checksum remains the integrity control.
var ASSETS = {
  registry: 'projects/stickleback-507923/assets/stickleback_validation/' +
      'app_current/validation_app_registry_current'
};

// The registry is an approved, one-feature pointer with these required string
// properties: pilot_output_asset_id, osm_matches_asset_id,
// copernicus_windows_asset_id, app_release_id, and registry_checksum_sha256.
// It is the only mutable App asset. Its three referenced collections are
// immutable evidence releases and are never reconstructed by the App.
var registry = ee.FeatureCollection(ASSETS.registry);
var pilotSites;
var osmMatches;
var copernicusWindows;
var registryProperties;

var map = ui.Map();
map.setControlVisibility({all: true, layerList: true});
var details = ui.Panel({style: {stretch: 'both', margin: '8px 0 0 0'}});
var statusLabel = ui.Label('Loading approved current release…', {margin: '6px 0'});
var selector = ui.Select({placeholder: 'Choose a validation site',
  style: {stretch: 'horizontal'}});
var assessment = ui.Select({items: ['not reviewed', 'looks consistent',
  'needs follow-up'], value: 'not reviewed', style: {stretch: 'horizontal'}});
// The Code Editor UI API exposes a single-line Textbox, not Textarea.  These
// values remain entirely in the browser; a single-line JSON record is easier
// to select and copy from the supported widget.
var note = ui.Textbox({placeholder: 'Optional note (browser memory only)',
  style: {stretch: 'horizontal'}});
var reviewerName = ui.Textbox({placeholder: 'Optional reviewer name (browser memory only)',
  style: {stretch: 'horizontal'}});
var review = ui.Textbox({placeholder: 'Copyable review record appears here.',
  style: {stretch: 'horizontal'}});
var selectedId = null;

function value(v) { return v === null || v === undefined || v === '' ? 'null' : String(v); }
function prop(props, key) {
  return props && Object.prototype.hasOwnProperty.call(props, key) ? props[key] : null;
}
function mergedProperties(base, overrides) {
  var merged = {};
  var key;
  base = base || {};
  overrides = overrides || {};
  for (key in base) {
    if (Object.prototype.hasOwnProperty.call(base, key)) merged[key] = base[key];
  }
  for (key in overrides) {
    if (Object.prototype.hasOwnProperty.call(overrides, key)) merged[key] = overrides[key];
  }
  return merged;
}
function heading(text) {
  details.add(ui.Label(text, {fontWeight: 'bold', margin: '12px 0 3px 0', color: '#17365d'}));
}
function subheading(text) {
  details.add(ui.Label(text, {fontWeight: 'bold', margin: '7px 0 2px 0',
    fontSize: '12px', color: '#4a4a4a'}));
}
function rows(props, fields) {
  fields.forEach(function(field) {
    details.add(ui.Label(field[0] + ': ' + value(prop(props, field[1])),
      {fontSize: '11px', margin: '1px 0'}));
  });
}
function suppressAdditionalProperty(key) {
  // These are either duplicates of labelled evidence above, local file paths,
  // raw diagnostics, or implementation metadata.  Future unfamiliar fields
  // (for example climate evidence) remain visible without App source changes.
  var prefixes = ['site_', 'topography_', 'merit_hydro_', 'osm_',
    'registry_', 'app_current_'];
  var assetMetadata = ['pilot_output_asset_id', 'osm_matches_asset_id',
    'copernicus_windows_asset_id'];
  var i;
  if (key === 'topography_provenance_path' || key === 'osm_failure_diagnostics') {
    return true;
  }
  if (assetMetadata.indexOf(key) !== -1) return true;
  for (i = 0; i < prefixes.length; i += 1) {
    if (key.indexOf(prefixes[i]) === 0) return true;
  }
  return false;
}
function extraRows(props, displayed) {
  var known = {};
  displayed.forEach(function(field) { known[field[1]] = true; });
  Object.keys(props || {}).sort().forEach(function(key) {
    if (!known[key] && key.indexOf('system:') !== 0 &&
        !suppressAdditionalProperty(key)) {
      details.add(ui.Label(key + ': ' + value(props[key]),
        {fontSize: '11px', margin: '1px 0'}));
    }
  });
}
function render(siteFeature, osmFeature, windowFeature) {
  // Registry metadata is release-wide. Site fields are applied afterwards so
  // original per-site provenance always wins if the names overlap.
  var site = mergedProperties(registryProperties,
      siteFeature ? siteFeature.properties : {});
  var osm = osmFeature ? osmFeature.properties : {};
  var windowProps = windowFeature ? windowFeature.properties : {};
  details.clear();
  heading('Release and input evidence');
  subheading('Site and environmental context');
  var siteFields = [['Sample ID', 'sample_id'],
    ['Population name', 'population_name'],
    ['Population abbreviation', 'population_abbreviation'],
    ['Latitude', 'latitude'], ['Longitude', 'longitude'], ['Ecotype', 'ecotype']];
  var releaseFields = [['Release ID', 'app_release_id'],
    ['Run ID', 'run_id'], ['Run version', 'run_version'],
    ['Output checksum (SHA-256)', 'staged_output_checksum_sha256']];
  rows(site, siteFields);
  subheading('Release and data integrity');
  rows(site, releaseFields);
  heading('OSM match');
  subheading('Match metrics');
  rows(osm, [['OSM type', 'selected_osm_type'], ['OSM ID', 'selected_osm_id'],
    ['Water feature class', 'water_feature_class'], ['Match method', 'match_method'],
    ['Match distance (m)', 'match_distance_m'], ['Match status', 'match_status']]);
  subheading('Snapshot and data integrity');
  rows(osm, [['Snapshot UTC', 'snapshot_utc'],
    ['Snapshot checksum (SHA-256)', 'snapshot_checksum_sha256']]);
  heading('Stored Copernicus terrain result');
  subheading('Environmental metrics');
  rows(site, [['Terrain status', 'terrain_status'], ['Elevation (m)', 'terrain_elevation_m'],
    ['Slope (degrees)', 'terrain_slope_degrees'], ['Local relief (m)', 'terrain_local_relief_m']]);
  subheading('Window and data integrity');
  rows(site, [['Window checksum (SHA-256)', 'copernicus_window_checksum_sha256'],
    ['Source URL', 'copernicus_source_url'], ['Retrieval UTC', 'copernicus_retrieval_utc']]);
  rows(windowProps, [['Window status', 'window_status'], ['Window resolution (m)', 'resolution_m']]);
  heading('MERIT Hydro point values');
  subheading('Environmental metrics');
  rows(site, [['Elevation (elv, m)', 'merit_elv'],
    ['Flow direction (dir, D8 code)', 'merit_dir'],
    ['Upstream drainage area (upa, km²)', 'merit_upa'],
    ['Upstream drainage pixels (upg, count)', 'merit_upg'],
    ['Height above nearest drainage (hnd, m)', 'merit_hnd'],
    ['Water-body mask (wat, categorical)', 'merit_wat'],
    ['River channel width (wth, m)', 'merit_wth']]);
  subheading('Data quality and interpretation');
  rows(site, [['Dataset', 'merit_dataset'], ['Scale (m)', 'merit_sampling_scale_m'],
    ['Elevation (elv) data status', 'merit_elv_status'],
    ['Flow direction (dir) data status', 'merit_dir_status'],
    ['Upstream drainage area (upa) data status', 'merit_upa_status'],
    ['Upstream drainage pixels (upg) data status', 'merit_upg_status'],
    ['Height above nearest drainage (hnd) data status', 'merit_hnd_status'],
    ['Water-body mask (wat) data status', 'merit_wat_status'],
    ['River channel width (wth) data status', 'merit_wth_status'],
    ['Catchment delineation status', 'hydrology_status'],
    ['Catchment delineation note', 'hydrology_message']]);
  heading('Runtime and provenance');
  subheading('Runtime metrics');
  rows(site, [['Site wall time (s)', 'site_runtime_wall_time_s'],
    ['EE client round-trip (s)', 'ee_client_round_trip_s'],
    ['EE timing definition', 'ee_timing_definition']]);
  subheading('Current-channel provenance');
  rows(site, [['Current-channel provenance', 'app_current_provenance']]);
  heading('Additional stored properties');
  extraRows(site, siteFields.concat(releaseFields).concat([
    ['Terrain status', 'terrain_status'], ['Elevation (m)', 'terrain_elevation_m'],
    ['Slope (degrees)', 'terrain_slope_degrees'], ['Local relief (m)', 'terrain_local_relief_m'],
    ['Window checksum (SHA-256)', 'copernicus_window_checksum_sha256'],
    ['Source URL', 'copernicus_source_url'], ['Retrieval UTC', 'copernicus_retrieval_utc'],
    ['Dataset', 'merit_dataset'], ['Scale (m)', 'merit_sampling_scale_m'],
    ['elv / status', 'merit_elv'], ['elv classification', 'merit_elv_status'],
    ['dir / status', 'merit_dir'], ['dir classification', 'merit_dir_status'],
    ['upa / status', 'merit_upa'], ['upa classification', 'merit_upa_status'],
    ['upg / status', 'merit_upg'], ['upg classification', 'merit_upg_status'],
    ['hnd / status', 'merit_hnd'], ['hnd classification', 'merit_hnd_status'],
    ['wat / status', 'merit_wat'], ['wat classification', 'merit_wat_status'],
    ['wth / status', 'merit_wth'], ['wth classification', 'merit_wth_status'],
    ['Catchment delineation status', 'hydrology_status'],
    ['Catchment delineation note', 'hydrology_message'],
    ['Site wall time (s)', 'site_runtime_wall_time_s'],
    ['EE client round-trip (s)', 'ee_client_round_trip_s'],
    ['EE timing definition', 'ee_timing_definition'],
    ['Current-channel provenance', 'app_current_provenance']
  ]));
}
function selectSite(id) {
  if (!id) return;
  selectedId = id;
  statusLabel.setValue('Loading approved current evidence for ' + id + '…');
  var site = pilotSites.filter(ee.Filter.eq('sample_id', id)).first();
  var osm = osmMatches.filter(ee.Filter.eq('sample_id', id)).first();
  var window = copernicusWindows.filter(ee.Filter.eq('sample_id', id)).first();
  map.layers().set(3, ui.Map.Layer(pilotSites.filter(ee.Filter.eq('sample_id', id))
      .style({color: 'ffff00', pointSize: 8, width: 2}), {}, 'Selected pilot point'));
  map.layers().set(4, ui.Map.Layer(osmMatches.filter(ee.Filter.eq('sample_id', id))
      .style({color: '00ffff', fillColor: '00000000', width: 3}), {}, 'Selected frozen OSM feature'));
  map.layers().set(5, ui.Map.Layer(copernicusWindows.filter(ee.Filter.eq('sample_id', id))
      .style({color: 'ff9900', fillColor: '00000000', width: 2}), {}, 'Selected Copernicus window'));
  site.evaluate(function(siteValue) { osm.evaluate(function(osmValue) {
    window.evaluate(function(windowValue) {
      render(siteValue, osmValue, windowValue);
      statusLabel.setValue('Showing approved current evidence for ' + id +
          '. Null means stored absent/no-data, never zero.');
    });
  }); });
  map.centerObject(site, 12);
}
selector.onChange(selectSite);

var makeReview = ui.Button({label: 'Prepare review record for copying',
  onClick: function() {
    if (!selectedId) { review.setValue('Select a validation site first.'); return; }
    review.setValue(JSON.stringify({sample_id: selectedId,
      app_release_id: prop(registryProperties, 'app_release_id'),
      registry_checksum_sha256: prop(registryProperties, 'registry_checksum_sha256'),
      assessment: assessment.getValue(),
      reviewer_name: reviewerName.getValue(),
      reviewer_note: note.getValue(),
      review_created_at_utc: new Date().toISOString(),
      viewer_notice: 'Created in browser memory only; not saved or submitted by this app.'}));
  }, style: {stretch: 'horizontal'}});
var sidebar = ui.Panel({style: {width: '390px', padding: '8px'}});
sidebar.add(ui.Label('Stickleback validation: approved current release',
  {fontWeight: 'bold', fontSize: '16px', color: '#17365d'}));
sidebar.add(ui.Label('Read-only inspection of the approved registry release. This App does not recalculate values or change assets.',
  {whiteSpace: 'pre-wrap', margin: '6px 0'}));
sidebar.add(selector); sidebar.add(statusLabel); sidebar.add(details);
sidebar.add(ui.Label('Human review (client-side only)', {fontWeight: 'bold', margin: '16px 0 3px 0'}));
sidebar.add(ui.Label('Nothing entered is persisted, submitted, or written to Earth Engine. Copy the generated text into an approved review record.',
  {whiteSpace: 'pre-wrap', fontSize: '11px'}));
sidebar.add(assessment); sidebar.add(reviewerName); sidebar.add(note);
sidebar.add(makeReview); sidebar.add(review);
ui.root.clear(); ui.root.add(ui.SplitPanel({firstPanel: sidebar, secondPanel: map, wipe: false}));
function initializeMap() {
  map.addLayer(pilotSites.style({color: 'e31a1c', pointSize: 5}), {}, 'All current pilot points');
  map.addLayer(osmMatches.style({color: '1f78b4', fillColor: '00000000', width: 1}), {}, 'All current OSM evidence', false);
  map.addLayer(copernicusWindows.style({color: 'ff7f00', fillColor: '00000000', width: 1}), {}, 'All current Copernicus windows', false);
  map.addLayer(ee.FeatureCollection([]), {}, 'Selected pilot point');
  map.addLayer(ee.FeatureCollection([]), {}, 'Selected frozen OSM feature');
  map.addLayer(ee.FeatureCollection([]), {}, 'Selected Copernicus window');
  map.setCenter(0, 45, 2);
  map.onClick(function(coords) {
    pilotSites.filterBounds(ee.Geometry.Point([coords.lon, coords.lat]).buffer(25000))
        .aggregate_array('sample_id').evaluate(function(ids) {
          if (ids && ids.length) selector.setValue(ids.sort()[0], true);
          else statusLabel.setValue('No validation point is within 25 km of that click.');
        });
  });
  pilotSites.aggregate_array('sample_id').evaluate(function(ids) {
    if (!ids || !ids.length) { statusLabel.setValue('The approved current release has no sites.'); return; }
    ids.sort(); selector.items().reset(ids);
    statusLabel.setValue(ids.length + ' current-release sites loaded. Select or click a point.');
  });
}
registry.first().evaluate(function(registryFeature) {
  registryProperties = registryFeature && registryFeature.properties;
  var required = ['pilot_output_asset_id', 'osm_matches_asset_id',
    'copernicus_windows_asset_id', 'app_release_id', 'registry_checksum_sha256'];
  if (!registryProperties || required.some(function(key) { return !registryProperties[key]; })) {
    statusLabel.setValue('Registry is missing required approved-release properties.');
    return;
  }
  pilotSites = ee.FeatureCollection(registryProperties.pilot_output_asset_id);
  osmMatches = ee.FeatureCollection(registryProperties.osm_matches_asset_id);
  copernicusWindows = ee.FeatureCollection(registryProperties.copernicus_windows_asset_id);
  initializeMap();
});
