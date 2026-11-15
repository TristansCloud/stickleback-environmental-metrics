"""Whole-band statistics on cached Copernicus GLO-90 native cell centres."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request

import numpy as np
import rasterio
from rasterio.windows import Window, from_bounds
from shapely import contains_xy, transform
from shapely.geometry import shape

from enviro_data.local_dem import tile_identity
from enviro_data.osm_disk import require_space
from enviro_data.osm_http import bounded_urlopen
from enviro_data.river_sources import sha

VERSION = 1
MAX_TILE_BYTES = 8_000_000
DEFAULT_CELL_BUDGET = 1_000_000


class GeometryBudgetError(ValueError):
    pass


def make_zones(geometry, cell_budget=DEFAULT_CELL_BUDGET):
    water = shape(geometry)
    if not water.is_valid or water.is_empty or water.geom_type not in {'Polygon', 'MultiPolygon'}:
        raise ValueError('valid whole-lake polygon required')
    lon, lat = water.representative_point().coords[0]
    sx, sy = 111195 * math.cos(math.radians(lat)), 111195
    if sx < 1000:
        raise GeometryBudgetError('polar local projection unsupported')
    projected = transform(water, lambda xy: np.column_stack(((xy[:, 0]-lon)*sx, (xy[:, 1]-lat)*sy)))
    west, south, east, north = projected.bounds
    if max(east-west, north-south) > 200000:
        raise GeometryBudgetError('lake exceeds 200 km local projection bound')
    regions = {'lake_surface': projected.buffer(-90)}
    interior_empty = regions['lake_surface'].is_empty
    previous = projected
    for radius in (50, 100, 250):
        outer = projected.buffer(radius)
        regions[f'shore_{radius}m'] = outer.difference(previous)
        previous = outer
    inverse = lambda xy: np.column_stack((xy[:, 0]/sx+lon, xy[:, 1]/sy+lat))
    zones = {key: transform(value, inverse) for key, value in regions.items()}
    outer = transform(previous, inverse)
    w, s, e, n = outer.bounds
    # GLO-90 has at most 1200 cells per degree; high-latitude tiles are narrower.
    estimated = (math.ceil((e-w)*1200)+4)*(math.ceil((n-s)*1200)+4)
    if estimated > cell_budget:
        raise GeometryBudgetError(f'lake bounding window exceeds {cell_budget:,} native cells ({estimated:,} estimated)')
    tiles = [(x, y) for x in range(math.floor(w), math.floor(e)+1)
             for y in range(math.floor(s), math.floor(n)+1)]
    if len(tiles) > 20:
        raise GeometryBudgetError('lake request exceeds 20 DEM tiles')
    return zones, outer.bounds, tiles, {'surface_inset_empty': interior_empty, 'estimated_bbox_cells': estimated}


def cached_tile(lon, lat, directory, live=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem, url = tile_identity(lon, lat)
    path = directory / (stem + '.tif')
    if not path.exists():
        if not live:
            raise RuntimeError('DEM tile missing; live download disabled')
        require_space(directory, MAX_TILE_BYTES)
        with bounded_urlopen(Request(url), timeout=35) as response:
            raw = response.read(MAX_TILE_BYTES+1)
        if len(raw) > MAX_TILE_BYTES:
            raise ValueError('DEM tile exceeds 8 MB download bound')
        require_space(directory, len(raw))
        temp = path.with_suffix('.part')
        temp.write_bytes(raw)
        try:
            with rasterio.open(temp) as ds:
                if ds.crs != rasterio.crs.CRS.from_epsg(4326):
                    raise ValueError('DEM CRS mismatch')
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
    return path, {'url': url, 'sha256': sha(path), 'bytes': path.stat().st_size,
                  'tile_longitude': lon, 'tile_latitude': lat}


def reduce_tiles(zones, bounds, tiles, cell_budget=DEFAULT_CELL_BUDGET):
    """tiles contains (path, ownership) pairs; ownership is a degree tile or None."""
    values = {key: [] for key in zones}
    totals = {key: 0 for key in zones}
    scanned = 0
    grids = []
    for path, ownership in tiles:
        with rasterio.open(path) as ds:
            if ds.crs != rasterio.crs.CRS.from_epsg(4326) or ds.transform.b or ds.transform.d:
                raise ValueError('north-up EPSG:4326 native grid required')
            w, s, e, n = bounds
            w, s, e, n = max(w, ds.bounds.left), max(s, ds.bounds.bottom), min(e, ds.bounds.right), min(n, ds.bounds.top)
            if w >= e or s >= n:
                continue
            raw = from_bounds(w, s, e, n, ds.transform)
            c0, r0 = max(0, math.floor(raw.col_off)), max(0, math.floor(raw.row_off))
            c1, r1 = min(ds.width, math.ceil(raw.col_off+raw.width)), min(ds.height, math.ceil(raw.row_off+raw.height))
            scanned += (c1-c0)*(r1-r0)
            if scanned > cell_budget:
                raise GeometryBudgetError('actual native-cell read budget exceeded')
            win = Window(c0, r0, c1-c0, r1-r0)
            data = ds.read(1, window=win, masked=True)
            t = ds.window_transform(win)
            xs, ys = np.meshgrid(t.c+(np.arange(data.shape[1])+0.5)*t.a,
                                 t.f+(np.arange(data.shape[0])+0.5)*t.e)
            owned = np.ones(data.shape, dtype=bool)
            if ownership is not None:
                x, y = ownership
                # Copernicus tiles have border-centred pixels; avoid counting seams twice.
                owned &= (xs >= x-1e-10) & (xs < x+1-1e-10) & (ys >= y-1e-10) & (ys < y+1-1e-10)
            valid = ~np.ma.getmaskarray(data) & np.isfinite(data.data)
            for key, region in zones.items():
                if region.is_empty:
                    continue
                membership = contains_xy(region, xs, ys) & owned
                totals[key] += int(membership.sum())
                cells = data.data[membership & valid]
                if cells.size:
                    values[key].append(np.asarray(cells, dtype=np.float64))
            grids.append({'transform': list(ds.transform)[:6], 'width': ds.width, 'height': ds.height})
    arrays = {key: np.concatenate(chunks) if chunks else np.array([], dtype=float) for key, chunks in values.items()}
    return arrays, totals, scanned, grids


def summarize_cells(arrays, totals, incomplete=False):
    surface = arrays['lake_surface']
    proxy = float(np.median(surface)) if len(surface) else None
    spread = float(np.ptp(surface)) if len(surface) else None
    stable = len(surface) >= 3 and len(surface) >= math.ceil(totals['lake_surface']*.75) and spread <= 5
    status = 'source_tiles_incomplete' if incomplete else 'exploratory' if stable else 'lake_surface_proxy_unstable_or_insufficient'
    stable = stable and not incomplete
    output = {'shoreline_elevation_status': status, 'has_shoreline_profile': stable,
              'shoreline_method': 'all_valid_native_cell_centres', 'shoreline_sampling_version': VERSION,
              'shoreline_elevation_source': 'Copernicus GLO-90 DSM; native cells; no resampling',
              'shoreline_buffer_definition': 'disjoint exterior bands 0-50,50-100,100-250 m; includes island shores',
              'lake_surface_dem_proxy_m': proxy, 'lake_surface_dem_range_m': spread,
              'lake_surface_valid_cell_count': int(len(surface)), 'lake_surface_total_cell_count': totals['lake_surface']}
    for radius in (50, 100, 250):
        key = f'shore_{radius}m'
        data = arrays[key]
        output.update({key+'_cell_count': int(len(data)), key+'_total_cell_count': totals[key],
                       key+'_mean_terrain_elevation_m': float(np.mean(data)) if len(data) else None,
                       key+'_mean_relative_elevation_m': float(np.mean(data)-proxy) if stable and len(data) else None,
                       key+'_median_relative_elevation_m': float(np.median(data)-proxy) if stable and len(data) else None,
                       key+'_p90_relative_elevation_m': float(np.percentile(data,90)-proxy) if stable and len(data) else None})
    return output


def collect(feature, cache, live=False, cell_budget=DEFAULT_CELL_BUDGET):
    zones, bounds, required, metadata = make_zones(feature['geometry'], cell_budget)
    tiles, sources, errors = [], [], []
    for x, y in required:
        try:
            path, source = cached_tile(x, y, cache, live)
            tiles.append((path, (x,y)))
            sources.append(source)
        except Exception as error:
            errors.append({'tile': [x,y], 'error': str(error)})
    arrays, totals, scanned, grids = reduce_tiles(zones, bounds, tiles, cell_budget)
    return {**summarize_cells(arrays, totals, bool(errors)), **metadata,
            'native_window_cells_read': scanned, 'sources': sources, 'errors': errors, 'native_grids': grids}


def cache_key(feature, cell_budget):
    identity = {'feature': feature, 'version': VERSION, 'dataset': 'Copernicus GLO-90',
                'cell_budget': cell_budget, 'surface_inset_m': 90, 'bands_m': [50,100,250],
                'projection': 'local_tangent_plane', 'membership': 'native_cell_centre', 'surface_range_limit_m': 5}
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
