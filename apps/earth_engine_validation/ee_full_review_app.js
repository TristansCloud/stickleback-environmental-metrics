/** Public full-dataset review App. Frozen measurements; imagery is context only.
 * Generate a configured copy with scripts/configure_ee_full_review.py.
 * No writes, live OSM queries or environmental sampling are performed here.
 */
var ROOT = 'REPLACE_WITH_FULL_REVIEW_ASSET_ROOT';
if (ROOT.indexOf('REPLACE_WITH_') === 0) throw new Error('Configure the uploaded full-review release first.');
var RELEASE = ROOT.split('/').pop();
var sites = ee.FeatureCollection(ROOT + '/sites');
var MERIT_ROOT = 'REPLACE_WITH_MERIT_MAXIMA_ASSET';
var meritMaxima = MERIT_ROOT.indexOf('REPLACE_WITH_') === 0 ? null : ee.FeatureCollection(MERIT_ROOT);
function attachMerit(feature) {
  feature = ee.Feature(feature);
  var id = feature.get('sample_id');
  var result = meritMaxima.filter(ee.Filter.eq('sample_id', id)).first();
  var combined = ee.Feature(feature.set(ee.Feature(result).toDictionary()));
  var earlier = combined.propertyNames().filter(ee.Filter.stringStartsWith('item','river_'));
  return combined.select(combined.propertyNames().removeAll(earlier));
}
var LOOKUP_ROOT = 'REPLACE_WITH_LOOKUP_ASSET';
var lookup = LOOKUP_ROOT.indexOf('REPLACE_WITH_') === 0 ? null : ee.FeatureCollection(LOOKUP_ROOT);
var lakes = ee.FeatureCollection(ROOT + '/lake_candidates');
var rivers = ee.FeatureCollection(ROOT + '/river_candidates');
var shorelineSamples = ee.FeatureCollection(ROOT + '/shoreline_samples');
var map = ui.Map();
map.setOptions('HYBRID');
map.setControlVisibility({all: true});
map.setCenter(-30, 55, 3);
var colors = {lake: '38bdf8', stream: 'a3e635', marine: '818cf8', transition: 'fb923c', unknown: 'cbd5e1'};
var generation = 0, current = null, index = [], visibleIndex = [];
var panel = ui.Panel({style: {width: '410px', padding: '16px', backgroundColor: '#f8fafc'}});
var details = ui.Panel();
var status = ui.Label('Loading release…', {color: '#475569', whiteSpace: 'pre-wrap'});
function label(text, style, url) { return ui.Label(text, style || {}, url); }
function section(title) { details.add(label(title, {fontWeight: 'bold', fontSize: '15px', margin: '18px 0 6px'})); }
function note(text) { details.add(label(text, {fontSize: '11px', color: '#64748b', whiteSpace: 'pre-wrap'})); }
function missing(v) { return v === null || v === undefined || v === ''; }
function number(v, digits, unit, scale) {
  if (missing(v) || !isFinite(Number(v))) return 'Unavailable';
  var value = Number(v) / (scale || 1);
  if (Math.abs(value) < Math.pow(10, -digits) / 2) value = 0;
  return value.toFixed(digits) + (unit ? ' ' + unit : '');
}
function metric(title, key, digits, unit, scale) {
  details.add(label(title + ': ' + number(current[key], digits, unit, scale), {fontSize: '12px', margin: '3px 0'}));
}
function text(title, key) { details.add(label(title + ': ' + (missing(current[key]) ? 'Unavailable' : String(current[key])),
  {fontSize: '12px', whiteSpace: 'pre-wrap', margin: '3px 0'})); }
var search = ui.Textbox({placeholder: 'Search sample ID or population name', style: {stretch: 'horizontal'}});
var habitat = ui.Select({items: ['All habitats', 'lake', 'stream', 'marine', 'transition', 'unknown'], value: 'All habitats', style: {stretch: 'horizontal'}});
var coverage = ui.Select({items: ['All coverage', 'Lake polygon available', 'Shoreline profile available', 'Lake polygon missing'],
  value: 'All coverage', style: {stretch: 'horizontal'}});
var selector = ui.Select({placeholder: 'Select a study site', style: {stretch: 'horizontal'}});
var imagery = ui.Select({items: ['Google satellite + labels', 'Google satellite', 'Google terrain', 'Vector only', 'Sentinel-2 clear composite'],
  value: 'Google satellite + labels', style: {stretch: 'horizontal'}});
var imageryYear = ui.Select({items: ['2025', '2024', '2023', '2022', '2021', '2020'], value: '2025'});
var imageryStatus = label('Google imagery is contextual; dates vary by location.', {fontSize: '11px', whiteSpace: 'pre-wrap'});
var satelliteLayer = ui.Map.Layer(ee.Image(0).selfMask(), {}, 'Sentinel-2 cloud-masked composite', false);
var allLayer = ui.Map.Layer(ee.FeatureCollection([]), {}, 'Study sites by provisional habitat');
var lakeLayer = ui.Map.Layer(lakes.style({color: '22d3ee', fillColor: '22d3ee18', width: 1}), {}, 'All lake candidates — identity unverified', false);
var selectedLakeLayer = ui.Map.Layer(ee.FeatureCollection([]), {}, 'Selected lake candidate');
var sampleLayer = ui.Map.Layer(ee.FeatureCollection([]), {}, 'Shoreline DEM sampling locations — not independent cells', false);
var lookupBox = ui.Map.Layer(ee.FeatureCollection([]), {}, 'ArcGIS query bounds', false);
var lookupVectors = ui.Map.Layer(ee.FeatureCollection([]), {}, 'Closest eligible lookup vectors');
var lookupStatus = label('Select a site to inspect lookup evidence.', {fontSize:'12px', whiteSpace:'pre-wrap'});
var lookupColors = {channel:'19b9e9', coast:'a78bfa', wetland:'84cc16', river_polygon:'2dd4bf', inland_water:'f59e0b', coastal_water:'60a5fa'};
var selectedPointLayer = ui.Map.Layer(ee.FeatureCollection([]), {}, 'Original sample coordinate');
[satelliteLayer, allLayer, lakeLayer, selectedLakeLayer, sampleLayer, lookupBox, lookupVectors, selectedPointLayer].forEach(function(layer) { map.layers().add(layer); });
var filter = ee.Filter;
var filtered = sites;
function applyFilters() {
  var query = (search.getValue() || '').toLowerCase().trim();
  var h = habitat.getValue(), c = coverage.getValue();
  visibleIndex = index.filter(function(row) {
    return (h === 'All habitats' || row.working_waterbody_type === h) &&
      (!query || (row.sample_id + ' ' + row.population_name).toLowerCase().indexOf(query) !== -1) &&
      (c !== 'Lake polygon available' || row.has_lake_polygon) &&
      (c !== 'Shoreline profile available' || row.has_shoreline_profile) &&
      (c !== 'Lake polygon missing' || (row.working_waterbody_type === 'lake' && !row.has_lake_polygon));
  });
  selector.items().reset(visibleIndex.map(function(row) { return {label: row.sample_id + ' · ' + row.population_name, value: row.sample_id}; }));
  filtered = sites.filter(filter.inList('sample_id', visibleIndex.map(function(row) { return row.sample_id; })));
  allLayer.setEeObject(filtered.map(function(feature) {
    var color = ee.Dictionary(colors).get(feature.get('working_waterbody_type'), 'cbd5e1');
    return feature.set('map_style', {color: color, pointSize: 5, width: 1});
  }).style({styleProperty: 'map_style'}));
  status.setValue(visibleIndex.length + ' / ' + index.length + ' sites match. All habitat labels and waterbody matches remain provisional.');
}
search.onChange(function() {
  applyFilters();
  var query = (search.getValue() || '').trim().toUpperCase();
  if (visibleIndex.length === 1 && visibleIndex[0].sample_id === query) {
    selector.setValue(query, false);
    showSite(query);
  }
});
habitat.onChange(applyFilters); coverage.onChange(applyFilters);
function updateImagery() {
  var choice = imagery.getValue();
  var clear = choice === 'Sentinel-2 clear composite';
  satelliteLayer.setShown(clear);
  var vectorsOnly = choice === 'Vector only';
  selectedLakeLayer.setShown(!vectorsOnly);
  lookupBox.setShown(Boolean(lookup) && vectorsOnly);
  if (vectorsOnly) {
    map.setOptions('Vectors', {Vectors: [{stylers: [{visibility: 'off'}]}]});
    imageryStatus.setValue(lookup ? 'Gray outline: ArcGIS query box. Colored lines: selected candidates.' : 'Vector view of the frozen evidence.');
    return;
  }
  if (!clear) {
    map.setOptions(choice === 'Google terrain' ? 'TERRAIN' : choice === 'Google satellite' ? 'SATELLITE' : 'HYBRID');
    imageryStatus.setValue('Google imagery is contextual; dates vary by location.');
    return;
  }
  if (!current) { imageryStatus.setValue('Select a site to load its Sentinel-2 composite.'); return; }
  map.setOptions('SATELLITE');
  var id = current.sample_id, token = generation, year = imageryYear.getValue();
  // A bounded site-local annual composite. It does not alter the stored dataset.
  var roi = ee.Geometry.Point([current.longitude, current.latitude]).buffer(20000).bounds();
  var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(roi)
    .filterDate(year + '-01-01', String(Number(year) + 1) + '-01-01');
  var cs = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
  var clearImages = s2.linkCollection(cs, ['cs_cdf']).map(function(image) {
    return image.updateMask(image.select('cs_cdf').gte(0.60));
  });
  // Empty collections remain fully masked; never show a previous site's image.
  var empty = ee.Image.constant([0, 0, 0]).rename(['B4', 'B3', 'B2']).selfMask();
  var composite = ee.Image(ee.Algorithms.If(s2.size().gt(0), clearImages.select(['B4', 'B3', 'B2']).median(), empty)).clip(roi);
  satelliteLayer.setEeObject(composite);
  satelliteLayer.setVisParams({bands: ['B4', 'B3', 'B2'], min: 0, max: 2500, gamma: 1.15});
  satelliteLayer.setName('Sentinel-2 ' + year + ' · cloud-masked · 10 m · ' + id);
  imageryStatus.setValue('Loading ' + year + ' annual composite within 20 km; cloud masking does not remove snow or guarantee gap-free coverage.');
  s2.size().evaluate(function(count, error) {
    if (token !== generation || imagery.getValue() !== 'Sentinel-2 clear composite' || imageryYear.getValue() !== year) return;
    imageryStatus.setValue(error ? 'Sentinel-2 unavailable: ' + error : count + ' intersecting scenes · Jan–Dec ' + year +
      ' · clear-pixel median (Cloud Score+ ≥0.60), 10 m RGB. Gaps may show the Google basemap beneath. Seasonal water levels may differ.');
  });
}
imagery.onChange(updateImagery); imageryYear.onChange(updateImagery);
function chartClimate() {
  var months = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];
  var rows = months.map(function(m, i) { return ee.Feature(null, {month: i + 1,
    air: current['air_temperature_' + m + '_c'], rain: current['precipitation_' + m + '_mm_day']}); });
  var fc = ee.FeatureCollection(rows);
  details.add(ui.Chart.feature.byFeature(fc, 'month', ['air']).setChartType('LineChart').setOptions({
    title: 'Monthly mean air temperature', legend: {position: 'none'}, colors: ['#e16845'],
    hAxis: {title: 'Month', ticks: [1,3,6,9,12]}, vAxis: {title: '°C'}, height: 180, pointSize: 3}));
  details.add(ui.Chart.feature.byFeature(fc, 'month', ['rain']).setChartType('ColumnChart').setOptions({
    title: 'Monthly mean daily precipitation', legend: {position: 'none'}, colors: ['#0284c7'],
    hAxis: {title: 'Month', ticks: [1,3,6,9,12]}, vAxis: {title: 'mm/day'}, height: 180}));
}
function showSite(id, recenter) {
  if (!id) return;
  var token = ++generation;
  current = null; details.clear(); reviewOutput.setValue(''); reviewNotes.setValue('');
  reviewClass.setValue('unreviewed');
  status.setValue('Loading ' + id + '…');
  var point = sites.filter(filter.eq('sample_id', id));
  if (lookup) {
    var siteLookup = lookup.filter(filter.eq('sample_id', id));
    lookupStatus.setValue('Loading rule-based lookup…');
    lookupBox.setEeObject(siteLookup.filter(filter.eq('role','query_box')).style({color:'cbd5e1',width:2}));
    lookupVectors.setEeObject(siteLookup.filter(filter.inList('role',Object.keys(lookupColors))).filter(filter.neq('source','HydroRIVERS')).map(function(feature) {
      return feature.set('lookup_style', {color:ee.Dictionary(lookupColors).get(feature.get('role'))});
    }).style({styleProperty:'lookup_style', width:4}));
    siteLookup.filter(filter.eq('role','status')).first().evaluate(function(feature,error) {
      if (token !== generation) return;
      if (error || !feature) { lookupStatus.setValue('Lookup evidence unavailable.'); return; }
      var p = feature.properties;
      lookupStatus.setValue(p.lookup_status.replace(/_/g,' ') + (p.lookup_summary ? '\n' + p.lookup_summary : ''));
    });
  }
  selectedPointLayer.setEeObject(point.style({color: 'fb7185', pointSize: 9, width: 2}));
  selectedLakeLayer.setEeObject(lakes.filter(filter.eq('sample_id', id)).style({color: 'fde047', fillColor: 'fde04722', width: 4}));
  sampleLayer.setEeObject(shorelineSamples.filter(filter.eq('sample_id', id)).map(function(f) {
    return f.set('point_style', {color: ee.Dictionary({lake_surface: 'ffffff', shore_50m: 'fde047', shore_100m: 'fb923c', shore_250m: 'ef4444'}).get(f.get('group'), 'ffffff'), pointSize: 4});
  }).style({styleProperty: 'point_style'}));
  satelliteLayer.setShown(false);
  if (recenter !== false) map.centerObject(point, 13);
  ui.url.set('site', id);
  var detailFeature = meritMaxima ? attachMerit(point.first()) : point.first();
  detailFeature.evaluate(function(feature, error) {
    if (token !== generation) return;
    if (error || !feature) { status.setValue('Could not load ' + id + ': ' + (error || 'unknown ID')); return; }
    current = feature.properties;
    section(current.population_name + ' · ' + id);
    text('Original ecotype', 'source_ecotype'); text('Provisional habitat', 'working_waterbody_type');
    text('Classification status', 'classification_status');
    details.add(label('Original coordinate: ' + number(current.latitude, 5, '°') + ', ' + number(current.longitude, 5, '°'), {fontSize: '12px'}));
    note('Original coordinates are retained. Display rounding is not a statement of measurement accuracy.');
    section('Elevation & atmospheric climate');
    metric('Point DSM elevation', 'point_elevation_m', 0, 'm');
    metric('Mean annual air temperature', 'mean_annual_air_temperature_c', 1, '°C');
    metric('Mean daily precipitation', 'annual_mean_precipitation_mm_day', 2, 'mm/day');
    text('Climate baseline', 'climate_period');
    note('Open-Meteo / Copernicus GLO-90 point DSM; NASA POWER / MERRA-2 regional air climatology. Neither is a water temperature or bathymetry measurement.');
    if (current.climate_status === 'ok') chartClimate();
    section('Lake boundary & shape');
    text('Geometry status', 'lake_geometry_status'); text('Source', 'lake_geometry_source');
    metric('Surface area', 'lake_area_m2', 2, 'ha', 10000);
    metric('Total shoreline (including islands)', 'lake_perimeter_m', 3, 'km', 1000);
    metric('Area / shoreline', 'lake_area_perimeter_m', 0, 'm');
    metric('Shoreline development', 'lake_shoreline_development', 2, '');
    note('Candidate identity needs review. Shorelines retain source resolution; normalization is pending. HydroLAKES generally excludes lakes smaller than 10 ha.');
    if (current.lake_osm_id && current.lake_osm_type) details.add(label('View source OSM object', {color: '#0284c7'},
      'https://www.openstreetmap.org/' + current.lake_osm_type + '/' + current.lake_osm_id));
    section('Upstream drainage area · MERIT Hydro');
    text('Status', 'merit_status');
    metric('Maximum upstream drainage area', 'merit_max_upstream_area_km2', 2, 'km²');
    text('Extraction method', 'merit_method');
    metric('Native cells evaluated', 'merit_valid_cell_count', 0, '');
    note('Streams use the maximum native MERIT area within 150 m of the original point. Lakes use the maximum inside the selected polygon. Nearby tributaries or downstream channels can influence the maximum.');
    section('Exploratory shoreline terrain');
    text('Profile status', 'shoreline_elevation_status');
    metric('Lake-interior DSM proxy', 'lake_surface_dem_proxy_m', 0, 'm');
    ['50','100','250'].forEach(function(band, i) {
      metric(['0–50 m','50–100 m','100–250 m'][i] + ' mean relative elevation', 'shore_' + band + 'm_mean_relative_elevation_m', 0, 'm');
    });
    note('Copernicus GLO-90 DSM, including vegetation/buildings. The first band is narrower than a DEM cell; samples are not independent cells. These are elevation differences, not shoreline slope or depth. Toggle shoreline sampling locations in Layers: white = lake interior; yellow = 0–50 m; orange = 50–100 m; red = 100–250 m.');
    details.add(label('Depth estimate: ' + (missing(current.lake_depth_estimate_m) ? 'Not yet estimated' : number(current.lake_depth_estimate_m, 0, 'm')), {fontSize: '12px'}));
    text('Depth status', 'lake_depth_status');
    section('Stored evidence & provenance');
    var rawPanel = ui.Panel({style: {shown: false}});
    Object.keys(current).filter(function(key) { return key.indexOf('river_') !== 0; }).sort().forEach(function(key) {
      rawPanel.add(label(key + ': ' + (missing(current[key]) ? 'Unavailable' : String(current[key])),
        {fontSize: '10px', whiteSpace: 'pre-wrap', margin: '2px 0'}));
    });
    details.add(ui.Checkbox('Show full-precision source properties', false, function(v) { rawPanel.style().set('shown', v); }));
    details.add(rawPanel);
    status.setValue(id + ' loaded · ' + RELEASE);
    updateImagery();
  });
}
selector.onChange(function(id) { showSite(id); });
map.onClick(function(coords) {
  var token = generation;
  // Select only within 12 screen pixels, in the currently filtered site set.
  var near = filtered.filterBounds(ee.Geometry.Point([coords.lon, coords.lat]).buffer(map.getScale() * 12))
    .map(function(f) { return f.set('click_distance', f.geometry().distance(ee.Geometry.Point([coords.lon, coords.lat]))); })
    .sort('click_distance').limit(1);
  near.aggregate_array('sample_id').evaluate(function(ids, error) {
    if (token !== generation || error || !ids || !ids.length) return;
    selector.setValue(ids[0], false); showSite(ids[0], false);
  });
});
var reviewClass = ui.Select({items: ['unreviewed','lake','reservoir','pond','stream','marine','transition','other','uncertain'], value: 'unreviewed'});
var reviewNotes = ui.Textbox({placeholder: 'Identity, boundary, classification or coordinate notes', style: {stretch: 'horizontal'}});
var reviewOutput = ui.Textbox({placeholder: 'Copy your review record before switching sites', style: {stretch: 'horizontal'}});
var copyReview = ui.Button('Prepare review record for copying', function() {
  if (!current) { reviewOutput.setValue('Select a site first.'); return; }
  reviewOutput.setValue(JSON.stringify({sample_id: current.sample_id, app_release_id: RELEASE,
    source_bundle_sha256: current.source_bundle_sha256, reviewed_waterbody_class: reviewClass.getValue(),
    notes: reviewNotes.getValue(), reviewed_at_utc: new Date().toISOString(), notice: 'Manual reviewer opinion; not saved or submitted by this App.'}));
});
var downloadStatus = label('', {fontSize: '11px', whiteSpace: 'pre-wrap'});
var downloads = ui.Panel();
var download = ui.Button('Create full-precision dataset download links', function() {
  download.setDisabled(true); downloadStatus.setValue('Preparing links for this frozen release…');
  // EE only serializes stored assets; no resampling or measurement calculation.
  var exportSites = meritMaxima ? sites.map(attachMerit) : sites;
  exportSites.getDownloadURL({format: 'CSV', filename: RELEASE + '_sites'}, function(url, error) {
    if (error || !url) { downloadStatus.setValue('Download failed: ' + error); download.setDisabled(false); return; }
    downloads.clear(); downloads.add(label('All sites + measurements (CSV)', {color: '#0284c7'}, url));
    lakes.getDownloadURL({format: 'GEO_JSON', filename: RELEASE + '_lakes'}, function(lakeUrl, lakeError) {
      if (lakeUrl) downloads.add(label('Candidate lake boundaries (GeoJSON)', {color: '#0284c7'}, lakeUrl));
      var riverEvidence = lookup ? lookup.filter(ee.Filter.eq('role','channel')).filter(ee.Filter.neq('source','HydroRIVERS')) : ee.FeatureCollection([]);
      riverEvidence.getDownloadURL({format: 'GEO_JSON', filename: RELEASE + '_osm_channels'}, function(riverUrl, riverError) {
        if (riverUrl) downloads.add(label('OSM channel geometry (GeoJSON)', {color: '#0284c7'}, riverUrl));
        downloadStatus.setValue(lakeError || riverError ? 'Some GIS links could not be generated; retry.' : 'Full stored precision; candidate geometries remain unverified. Links expire.');
        download.setDisabled(false);
      });
    });
  });
});
panel.add(label('STICKLEBACK · ENVIRONMENTAL ATLAS', {fontSize: '11px', color: '#0284c7', fontWeight: 'bold'}));
panel.add(label('Explore the study sites', {fontSize: '24px', fontWeight: 'bold', color: '#0f172a'}));
panel.add(label('599 original sites · frozen review release', {fontSize: '13px', color: '#475569'}));
panel.add(search); panel.add(habitat); panel.add(coverage); panel.add(selector); panel.add(status);
panel.add(ui.Button('Show all matching sites', function() { if (visibleIndex.length) map.centerObject(filtered); }));
panel.add(label('Imagery & map layers', {fontWeight: 'bold', margin: '18px 0 6px'}));
panel.add(imagery); panel.add(ui.Panel([label('Composite year'), imageryYear], ui.Panel.Layout.flow('horizontal')));
panel.add(imageryStatus);
if (lookup) {
  panel.add(label('Closest eligible water features', {fontWeight:'bold'}));
  panel.add(lookupStatus);
  panel.add(label('Rule-based proposals. Marine and transition matches describe nearby context.', {fontSize:'11px', whiteSpace:'pre-wrap'}));
}
panel.add(label('Select a site to see its available evidence. The selected lake candidate has a yellow outline. Use map Layers to toggle evidence.', {fontSize: '11px', color: '#64748b', whiteSpace: 'pre-wrap'}));
var legend = ui.Panel({layout: ui.Panel.Layout.flow('horizontal')});
Object.keys(colors).forEach(function(key) { legend.add(label('● ' + key, {color: '#' + colors[key], fontSize: '10px', margin: '3px'})); });
panel.add(legend); panel.add(details);
panel.add(label('Reviewer notes', {fontWeight: 'bold', margin: '18px 0 6px'}));
panel.add(reviewClass); panel.add(reviewNotes); panel.add(copyReview); panel.add(reviewOutput);
panel.add(label('Notes stay in this browser only. Copy the record before changing site or closing the page.', {fontSize: '11px', whiteSpace: 'pre-wrap', color: '#64748b'}));
panel.add(download); panel.add(downloadStatus); panel.add(downloads);
panel.add(label('Release: ' + RELEASE, {fontSize: '10px', whiteSpace: 'pre-wrap'}));
panel.add(label('© OpenStreetMap contributors · ODbL', {fontSize: '10px'}, 'https://www.openstreetmap.org/copyright'));
panel.add(label('HydroLAKES v1.0 · CC BY 4.0 · Messager et al. (2016)', {fontSize: '10px'}, 'https://www.hydrosheds.org/products/hydrolakes'));
panel.add(label('HydroRIVERS v1.0 · Lehner & Grill (2013)', {fontSize: '10px'}, 'https://www.hydrosheds.org/products/hydrorivers'));
panel.add(label('Data sources, methods & limitations', {fontSize: '11px'}, 'https://github.com/TristansCloud/stickleback-environmental-metrics/blob/codex/provisional-habitat-pilots/docs/full_review_workflow.md'));
// A persistent toggle keeps the map accessible on narrow screens too.
var sidebarVisible = true;
var toggle = ui.Button('Show map / hide details', function() {
  sidebarVisible = !sidebarVisible;
  panel.style().set('shown', sidebarVisible);
  toggle.setLabel(sidebarVisible ? 'Show map / hide details' : 'Show site details');
});
map.style().set('stretch', 'both');
var toolbar = ui.Panel([toggle, label('Stickleback environmental review', {fontWeight: 'bold', margin: '10px'})], ui.Panel.Layout.flow('horizontal'));
var workspace = ui.Panel([panel, map], ui.Panel.Layout.flow('horizontal'), {stretch: 'both'});
ui.root.clear(); ui.root.setLayout(ui.Panel.Layout.flow('vertical')); ui.root.add(toolbar); ui.root.add(workspace);
var fields = ['sample_id','population_name','working_waterbody_type','has_lake_polygon','has_river_attributes','has_shoreline_profile'];
sites.select(fields).toList(1000).map(function(f) { return ee.Feature(f).toDictionary(fields); }).evaluate(function(rows, error) {
  if (error || !rows) { status.setValue('Could not load release. Check asset access: ' + error); return; }
  if (rows.length !== 599) { status.setValue('Release check failed: expected 599 sites, found ' + rows.length); return; }
  index = rows.sort(function(a,b) { return a.sample_id.localeCompare(b.sample_id); });
  applyFilters();
  var requested = ui.url.get('site');
  if (requested && index.some(function(r) { return r.sample_id === requested; })) {
    selector.setValue(requested, false); showSite(requested);
  }
});
