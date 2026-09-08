# MERIT Hydro Earth Engine smoke test — 2026-09-07

The authenticated Earth Engine client successfully read one point only:

- Site: `S0002` (freshwater), latitude `69.5856`, longitude `27.5854`
- Earth Engine project: `stickleback-507923`
- Dataset: `MERIT/Hydro/v1_0_1`
- Requested bands: `elv`, `dir`, `upa`, `upg`, `hnd`, `wat`, `wth`
- Sampling: `first` reducer, 90 m, `EPSG:4326`
- Earth Engine API: `1.7.42`
- Authentication call: not performed; existing local credentials were used
- Export submitted: no; raster downloaded: no

Observed result:

```text
elv = 310.70001220703125
dir = 8
upa = 0.006015514023602009
upg = 2
hnd = 5.100006103515625
wat = 0
wth = null (nodata_or_masked)
```

`wat = 0` is retained as a valid source value. `wth = null` is explicitly
classified as `nodata_or_masked`; no null or ocean/no-data value is converted
to elevation zero. The full JSON result and provenance checksum are cached at
`data/cache/merit_hydro/S0002_earth_engine_smoke.json` (the cache directory is
ignored by `.gitignore`).

Reusable command, from the project root after activating `.venv`:

```bash
python scripts/run_merit_earth_engine_smoke.py
```
