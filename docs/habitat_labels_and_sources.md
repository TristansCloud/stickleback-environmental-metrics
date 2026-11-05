# Habitat labels and current lake sources

The viewer uses provisional habitat labels from broad ecotypes, recognizable name terms, and documented Japanese place names and site-specific cached OSM watercourse evidence. The name parser recognizes Lakeside, Lac, Lago, Etang, Weiher, Bach, Kanal, Canal, Ruisseau, Riviere, Fiume, Torrente and the Japanese river suffix gawa. Camel-case words are split before matching, so AgaRiver is recognized.

Run refresh_site_labels.py with the repository path and an optional --output path to create a derived copy of the original review table. Only unknown working labels are changed. The original coordinates, ecotypes and input table are preserved. The reference records in data/habitat_name_evidence.csv include source URLs, evidence bases and review notes. These support place-name interpretation and remain provisional sampling-habitat labels.

The updates change 56 unknown labels, including 26 Swiss sites, five Japanese sites and 19 French, Spanish and Portuguese sites. The current totals are 229 lakes, 101 streams, 91 marine sites, 18 transition sites and 160 unknown sites.

The 19 additional watercourse labels use existing OSM geometry within 25 m of the original freshwater sample point: three French, eleven Spanish and five Portuguese sites. Stream includes canals. Their evidence supports a broad watercourse class and does not verify the named river, the sampling position or perennial flow. All retain required-review flags. Cases with competing lake, reservoir or wetland evidence remain unresolved; the Rio Minho point, for example, falls in a mapped reservoir. No general rule classifies every point by its closest vector.

Current lake selection accepts OSM geometry only, from the public replica, local Geofabrik OSM layers, or verified full OSM object retrieval. A containing polygon takes priority. Where no polygon contains the point, the nearest eligible polygon within 500 m is retained with a review flag.

Lake area, shoreline length and shape metrics are recomputed from the selected full OSM geometry. MERIT maxima use the same selected polygon. Current source fields and the lake-coverage filter come from the latest results table. Earlier lake fields are removed when the table is joined into the viewer. The current whole-band shoreline refresh uses the same selected OSM polygons. Earlier point-sampled profiles are replaced by native-cell statistics in the combined site-metrics table.

For known OSM objects, fetch_osm_lake_object.py retrieves and validates full ways or relations. The matching script can take a supplementary FeatureCollection as its seventh positional argument. Its feature properties must include sample_id, source, feature_id and OSM water tags. This supplies the three named Japanese lakes where the replica lacks an Asian polygon layer.

The Earth Engine display overlay uses complete selected inland-water outlines, including island rings, with a small topology-preserving display simplification. Query bounds remain available in the separate diagnostic atlas but are not rendered in the App. Stream display geometry is unchanged. Display simplification does not affect the full polygons used for lake metrics or MERIT reductions.

The legacy point-sampling command supports up to 200 deterministic samples per band. The new whole-band workflow supersedes that sampling cap: it uses every valid native cell centre in each band, subject to the documented geometry and cell-budget safeguards. See whole_band_shoreline.md for the method and reproducible commands.
