import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping, Polygon

from enviro_data.shoreline_full_band import make_zones, reduce_tiles, summarize_cells, GeometryBudgetError


def test_native_cells_are_not_resampled_and_nodata_is_excluded(tmp_path):
    path=tmp_path/'dem.tif'
    data=np.arange(100,dtype='float32').reshape(10,10)
    data[2,2]=-9999
    with rasterio.open(path,'w',driver='GTiff',width=10,height=10,count=1,dtype='float32',
                       crs='EPSG:4326',transform=from_origin(0,1,.1,.1),nodata=-9999) as ds:ds.write(data,1)
    regions={'lake_surface':box(.2,.2,.5,.5),'shore_50m':box(.5,.2,.8,.5),
             'shore_100m':box(0,0,.2,.2),'shore_250m':box(0,.7,.3,1)}
    arrays,totals,scanned,grids=reduce_tiles(regions,(0,0,1,1),[(path,None)])
    np.testing.assert_array_equal(np.sort(arrays['lake_surface']),np.sort(data[5:8,2:5].ravel()))
    assert totals['shore_250m']==9 and len(arrays['shore_250m'])==8
    assert scanned==100 and grids[0]['width']==10
    with pytest.raises(GeometryBudgetError):reduce_tiles(regions,(0,0,1,1),[(path,None)],99)


def test_bands_include_island_land_and_exclude_water():
    water=Polygon([(-.01,-.01),(.01,-.01),(.01,.01),(-.01,.01),(-.01,-.01)],
                  holes=[[(-.002,-.002),(.002,-.002),(.002,.002),(-.002,.002),(-.002,-.002)]])
    zones,_,_,_=make_zones(mapping(water))
    from shapely.geometry import Point
    assert zones['shore_50m'].contains(Point(.0018,0))
    assert not zones['shore_50m'].contains(Point(.003,0))
    assert zones['shore_50m'].intersection(zones['shore_100m']).area<1e-15
    assert zones['shore_100m'].intersection(zones['shore_250m']).area<1e-15
    with pytest.raises(GeometryBudgetError):make_zones(mapping(box(0,0,4,4)))


def test_full_band_statistics_and_missing_reference_do_not_invent_differences():
    arrays={'lake_surface':np.array([10,10,10]),'shore_50m':np.array([11,13]),
            'shore_100m':np.array([12,14,16]),'shore_250m':np.array([20,30])}
    totals={k:len(v) for k,v in arrays.items()}
    result=summarize_cells(arrays,totals)
    assert result['has_shoreline_profile']
    assert result['shore_100m_mean_relative_elevation_m']==4
    assert result['shore_100m_cell_count']==3
    assert not summarize_cells(arrays,totals,True)['has_shoreline_profile']
    arrays['lake_surface']=np.array([])
    result=summarize_cells(arrays,totals)
    assert not result['has_shoreline_profile'] and result['shore_100m_mean_relative_elevation_m'] is None
    assert result['shore_100m_mean_terrain_elevation_m']==14


def test_border_centred_native_cells_are_counted_once_across_tiles(tmp_path):
    paths=[]
    for west in (0,1):
        path=tmp_path/f"tile_{west}.tif"
        with rasterio.open(path,'w',driver='GTiff',width=3,height=3,count=1,dtype='float32',
                           crs='EPSG:4326',transform=from_origin(west-.25,1.25,.5,.5)) as ds:
            ds.write(np.ones((3,3),dtype='float32'),1)
        paths.append((path,(west,0)))
    region=box(-.1,-.1,1.9,.9)
    arrays,totals,_,_=reduce_tiles({'lake_surface':region},region.bounds,paths)
    assert totals['lake_surface']==8
    assert len(arrays['lake_surface'])==8
