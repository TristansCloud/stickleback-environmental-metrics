# Closest water lookup

The deterministic pass preserves all 599 original sites. Stream proposals use the closest eligible channel within 500 m. A second search extends to 1,500 m for context where the first pass yields no eligible evidence. Lakes require containment. Coastal, river, and wetland evidence remain separate. The two explicitly pelagic sites are skipped.

Run these commands from an external working directory for generated files. Set REPO to the checkout path. The inputs are the extracted Nov. 1 review bundle, the prepared Earth Engine release, and the Geofabrik coverage assignment JSON in their documented repository cache locations. Use the repo's Python environment with the earth-engine and local-osm extras.

```sh
python "$REPO/scripts/fetch_stickleback_replica.py" "$REPO"
python "$REPO/scripts/closest_water_599.py" "$REPO" - 1500 osm_replica_cache/site_features.json
python "$REPO/scripts/build_lookup_atlas.py"
python "$REPO/scripts/upload_lookup_overlay.py"
```

The first command sends non-pelagic search bounds to the ArcGIS-hosted OSM replica. Use it only with authorization for that data transfer. It omits site names and IDs, caches successful responses, and keeps at least 60 GB free. To include the 2025 Iceland water and waterway shapefiles, replace the dash in the second command with their directory. The script also uses cached small OSM boxes and the frozen river and lake candidates.

The output includes a CSV, a standalone vector atlas, and a geometry overlay. ArcGIS coverage lacks a global coastline layer and Asian water polygons. Candidate geometry is clipped and simplified for display. The upload command exports a separate private asset and verifies the count and all 599 status records. Use its asset ID with the existing configure command via `--lookup-asset`. In the Code Editor, select **Vector only** to display the query box. Earlier river evidence is available in Layers for comparison.
