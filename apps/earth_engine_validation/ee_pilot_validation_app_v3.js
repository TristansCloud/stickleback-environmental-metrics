/**
 * Restricted 40-site pilot validation viewer for the Earth Engine Code Editor.
 *
 * This is a read-only viewer.  It reads three immutable, versioned vector
 * assets that were prepared from the completed pilot run.  It performs no
 * environmental calculation, no raster sampling, and no writes.  Review text
 * is held only in the browser panel so a reviewer can copy it manually.
 *
 * Before pasting into the Code Editor, replace every REPLACE_WITH_* token
 * below with an immutable asset ID.  Do not point these constants at a mutable
 * alias such as "latest".
 */

var ASSETS = Object.freeze({
  pilotOutput:
      'projects/stickleback-507923/assets/stickleback_validation/' +
      'ee_app_validation_assets_v3_4e20cbe056b676f2/pilot_output',
  osmMatches:
      'projects/stickleback-507923/assets/stickleback_validation/' +
      'ee_app_validation_assets_v3_4e20cbe056b676f2/osm_matches',
  copernicusWindows:
      'projects/stickleback-507923/assets/stickleback_validation/' +
      'ee_app_validation_assets_v3_4e20cbe056b676f2/copernicus_windows'
});

function assertConfigured(assetIds) {
  Object.keys(assetIds).forEach(function(name) {
    if (assetIds[name].indexOf('REPLACE_WITH_') !== -1 ||
        assetIds[name].indexOf('YYYY_MM_DD') !== -1) {
      throw new Error('Set the immutable asset ID for ASSETS.' + name +
          ' before running this template.');
    }
  });
}

assertConfigured(ASSETS);

// These collections must be frozen exports of the completed 40-site run.
// They are deliberately the only application data sources.
var pilotSites = ee.FeatureCollection(ASSETS.pilotOutput);
var osmMatches = ee.FeatureCollection(ASSETS.osmMatches);
var copernicusWindows = ee.FeatureCollection(ASSETS.copernicusWindows);

var map = ui.Map();
map.setControlVisibility({all: true, layerList: true});

var detailPanel = ui.Panel({
  style: {stretch: 'both', margin: '8px 0 0 0', padding: '0'}
});
var statusLabel = ui.Label('Loading the frozen pilot index…', {
  color: '#555555', margin: '6px 0 0 0'
});
var siteSelector = ui.Select({
  placeholder: 'Choose a pilot site',
  style: {stretch: 'horizontal'}
});
var assessmentSelector = ui.Select({
  items: ['not reviewed', 'looks consistent', 'needs follow-up'],
  value: 'not reviewed',
  style: {stretch: 'horizontal'}
});
var noteBox = ui.Textarea({
  placeholder: 'Optional reviewer note (kept only in this browser session)',
  style: {stretch: 'horizontal', height: '72px'}
});
var reviewOutput = ui.Textarea({
  placeholder: 'A copyable review record will appear here.',
  style: {stretch: 'horizontal', height: '110px'},
  disabled: false
});
var selectedSiteId = null;

function displayValue(value) {
  return value === null || value === undefined || value === '' ? 'null' : String(value);
}

function property(props, name) {
  return props && Object.prototype.hasOwnProperty.call(props, name) ? props[name] : null;
}

function addSection(panel, title) {
  panel.add(ui.Label(title, {
    fontWeight: 'bold', margin: '12px 0 3px 0', color: '#17365d'
  }));
}

function addRows(panel, props, rows) {
  rows.forEach(function(row) {
    panel.add(ui.Label(row[0] + ': ' + displayValue(property(props, row[1])), {
      fontSize: '11px', margin: '1px 0'
    }));
  });
}

function setSelectionLayers(siteId) {
  var onlyThisSite = pilotSites.filter(ee.Filter.eq('sample_id', siteId));
  var onlyThisOsm = osmMatches.filter(ee.Filter.eq('sample_id', siteId));
  var onlyThisWindow = copernicusWindows.filter(ee.Filter.eq('sample_id', siteId));

  map.layers().set(3, ui.Map.Layer(
      onlyThisSite.style({color: 'ffff00', pointSize: 8, width: 2}), {},
      'Selected pilot point'));
  map.layers().set(4, ui.Map.Layer(
      onlyThisOsm.style({color: '00ffff', fillColor: '00000000', width: 3}), {},
      'Selected frozen OSM feature'));
  map.layers().set(5, ui.Map.Layer(
      onlyThisWindow.style({color: 'ff9900', fillColor: '00000000', width: 2}), {},
      'Selected Copernicus 3×3 window'));
}

function renderDetails(siteFeature, osmFeature, windowFeature) {
  var site = siteFeature ? siteFeature.properties : {};
  var osm = osmFeature ? osmFeature.properties : {};
  var windowProps = windowFeature ? windowFeature.properties : {};
  detailPanel.clear();

  addSection(detailPanel, 'Input coordinate and ecotype');
  addRows(detailPanel, site, [
    ['Sample ID', 'sample_id'], ['Latitude', 'latitude'], ['Longitude', 'longitude'],
    ['Ecotype', 'ecotype'], ['Population', 'population_name'],
    ['Population abbreviation', 'population_abbreviation']
  ]);

  addSection(detailPanel, 'Frozen OSM match');
  addRows(detailPanel, osm, [
    ['OSM type', 'selected_osm_type'], ['OSM ID', 'selected_osm_id'],
    ['Water feature class', 'water_feature_class'], ['Match method', 'match_method'],
    ['Match distance (m)', 'match_distance_m'], ['Snapshot UTC', 'snapshot_utc'],
    ['Snapshot checksum (SHA-256)', 'snapshot_checksum_sha256'],
    ['Match status', 'match_status']
  ]);

  addSection(detailPanel, 'Stored Copernicus terrain result');
  addRows(detailPanel, site, [
    ['Terrain status', 'terrain_status'], ['Elevation (m)', 'terrain_elevation_m'],
    ['Slope (degrees)', 'terrain_slope_degrees'], ['Local relief (m)', 'terrain_local_relief_m'],
    ['Window checksum (SHA-256)', 'copernicus_window_checksum_sha256'],
    ['Source URL', 'copernicus_source_url'], ['Retrieval UTC', 'copernicus_retrieval_utc']
  ]);
  addRows(detailPanel, windowProps, [
    ['Window status', 'window_status'], ['Window resolution (m)', 'resolution_m']
  ]);

  addSection(detailPanel, 'Stored MERIT Hydro point values');
  addRows(detailPanel, site, [
    ['Dataset', 'merit_dataset'], ['Scale (m)', 'merit_sampling_scale_m'],
    ['elv / status', 'merit_elv'], ['elv classification', 'merit_elv_status'],
    ['dir / status', 'merit_dir'], ['dir classification', 'merit_dir_status'],
    ['upa / status', 'merit_upa'], ['upa classification', 'merit_upa_status'],
    ['upg / status', 'merit_upg'], ['upg classification', 'merit_upg_status'],
    ['hnd / status', 'merit_hnd'], ['hnd classification', 'merit_hnd_status'],
    ['wat / status', 'merit_wat'], ['wat classification', 'merit_wat_status'],
    ['wth / status', 'merit_wth'], ['wth classification', 'merit_wth_status'],
    ['Hydrology status', 'hydrology_status'], ['Hydrology message', 'hydrology_message']
  ]);

  addSection(detailPanel, 'Run and cache provenance');
  addRows(detailPanel, site, [
    ['Run ID', 'run_id'], ['Run version', 'run_version'],
    ['Output checksum (SHA-256)', 'staged_output_checksum_sha256'],
    ['Site wall time (s)', 'site_runtime_wall_time_s'],
    ['EE client round-trip (s)', 'ee_client_round_trip_s'],
    ['EE timing definition', 'ee_timing_definition']
  ]);
}

function showSite(siteId) {
  if (!siteId) return;
  selectedSiteId = siteId;
  statusLabel.setValue('Loading frozen evidence for ' + siteId + '…');
  setSelectionLayers(siteId);

  var selected = pilotSites.filter(ee.Filter.eq('sample_id', siteId)).first();
  var selectedOsm = osmMatches.filter(ee.Filter.eq('sample_id', siteId)).first();
  var selectedWindow = copernicusWindows.filter(ee.Filter.eq('sample_id', siteId)).first();
  selected.evaluate(function(siteFeature) {
    selectedOsm.evaluate(function(osmFeature) {
      selectedWindow.evaluate(function(windowFeature) {
        renderDetails(siteFeature, osmFeature, windowFeature);
        statusLabel.setValue('Showing frozen evidence for ' + siteId +
            '. Null means absent/no-data in the stored pilot output, not zero.');
      });
    });
  });
  map.centerObject(selected, 12);
}

siteSelector.onChange(showSite);

var prepareReviewButton = ui.Button({
  label: 'Prepare review record for copying',
  onClick: function() {
    if (!selectedSiteId) {
      reviewOutput.setValue('Select a pilot site before preparing a review record.');
      return;
    }
    var record = {
      sample_id: selectedSiteId,
      assessment: assessmentSelector.getValue(),
      reviewer_note: noteBox.getValue(),
      viewer_notice: 'Created in browser memory only; not saved or submitted by this app.'
    };
    reviewOutput.setValue(JSON.stringify(record, null, 2));
  },
  style: {stretch: 'horizontal'}
});

var sidebar = ui.Panel({style: {width: '390px', padding: '8px'}});
sidebar.add(ui.Label('Stickleback 40-site pilot: validation viewer', {
  fontWeight: 'bold', fontSize: '16px', color: '#17365d'
}));
sidebar.add(ui.Label(
    'Read-only inspection of frozen pilot evidence. This viewer does not recalculate values or change assets.',
    {whiteSpace: 'pre-wrap', margin: '6px 0'}));
sidebar.add(siteSelector);
sidebar.add(statusLabel);
sidebar.add(detailPanel);
sidebar.add(ui.Label('Human review (client-side only)', {
  fontWeight: 'bold', margin: '16px 0 3px 0', color: '#17365d'
}));
sidebar.add(ui.Label(
    'Nothing entered here is persisted, submitted, or written to Earth Engine. ' +
    'Use the button to create text, then copy it manually into an approved review record.',
    {whiteSpace: 'pre-wrap', fontSize: '11px'}));
sidebar.add(assessmentSelector);
sidebar.add(noteBox);
sidebar.add(prepareReviewButton);
sidebar.add(reviewOutput);

ui.root.clear();
ui.root.add(ui.SplitPanel({firstPanel: sidebar, secondPanel: map, wipe: false}));

map.addLayer(pilotSites.style({color: 'e31a1c', pointSize: 5}), {}, 'All pilot points (frozen)');
map.addLayer(osmMatches.style({color: '1f78b4', fillColor: '00000000', width: 1}), {},
    'All matched OSM features (frozen)', false);
map.addLayer(copernicusWindows.style({color: 'ff7f00', fillColor: '00000000', width: 1}), {},
    'All Copernicus windows (frozen)', false);
map.addLayer(ee.FeatureCollection([]), {}, 'Selected pilot point');
map.addLayer(ee.FeatureCollection([]), {}, 'Selected frozen OSM feature');
map.addLayer(ee.FeatureCollection([]), {}, 'Selected Copernicus 3×3 window');
map.setCenter(0, 45, 2);

// Clicking close to a displayed pilot point is equivalent to selecting it from
// the list; this only filters the frozen point index and never recomputes data.
map.onClick(function(coords) {
  var click = ee.Geometry.Point([coords.lon, coords.lat]);
  pilotSites.filterBounds(click.buffer(25000)).aggregate_array('sample_id').evaluate(
      function(ids) {
        if (ids && ids.length) {
          siteSelector.setValue(ids.sort()[0], true);
        } else {
          statusLabel.setValue('No pilot point is within 25 km of that click.');
        }
      });
});

pilotSites.aggregate_array('sample_id').evaluate(function(ids) {
  if (!ids || !ids.length) {
    statusLabel.setValue('The configured pilot-output asset has no sites.');
    return;
  }
  ids.sort();
  siteSelector.items().reset(ids);
  statusLabel.setValue(ids.length + ' frozen pilot sites loaded. Select a point or click one on the map.');
});
