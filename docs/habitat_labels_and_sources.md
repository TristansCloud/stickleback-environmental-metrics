# Habitat labels and current lake sources

The viewer uses provisional habitat labels from broad ecotypes, recognizable name terms, and three documented Japanese place names. The name parser recognizes Lakeside, Lac, Lago, Etang, Weiher, Bach, Kanal, Canal, Ruisseau, Riviere, Fiume, Torrente and the Japanese river suffix gawa. Camel-case words are split before matching, so AgaRiver is recognized.

Run refresh_site_labels.py with the repository path and an optional --output path to create a derived copy of the original review table. Only unknown working labels are changed. The original coordinates, ecotypes and input table are preserved. The three reference records in data/habitat_name_evidence.csv include source URLs. These support place-name interpretation and remain provisional sampling-habitat labels.

The update changes 37 unknown labels, including 26 Swiss sites and five Japanese sites. The current totals are 229 lakes, 82 streams, 91 marine sites, 18 transition sites and 179 unknown sites.

Current lake selection accepts OSM geometry only, from the public replica, local Geofabrik OSM layers, or verified full OSM object retrieval. A containing polygon takes priority. Where no polygon contains the point, the nearest eligible polygon within 500 m is retained with a review flag.

Lake area, shoreline length and shape metrics are recomputed from the selected full OSM geometry. MERIT maxima use the same selected polygon. Current source fields and the lake-coverage filter come from the latest results table. Earlier lake fields are removed when the table is joined into the viewer. The older shoreline terrain profiles are labeled as earlier measurements because they predate this polygon selection.

For known OSM objects, fetch_osm_lake_object.py retrieves and validates full ways or relations. The matching script can take a supplementary FeatureCollection as its seventh positional argument. Its feature properties must include sample_id, source, feature_id and OSM water tags. This supplies the three named Japanese lakes where the replica lacks an Asian polygon layer.
