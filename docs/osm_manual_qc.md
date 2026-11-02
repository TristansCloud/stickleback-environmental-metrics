# Manual quality control queue

Recorded October 6, 2026. Open items below are not resolved by containment.

## S0512: South Twin Lake and Wickiup Reservoir — pending

- Sample coordinate: latitude 43.71231, longitude -121.77028.
- South Twin Lake: [OSM way 352410633](https://www.openstreetmap.org/way/352410633), `natural=water`, `water=lake`.
- Wickiup Reservoir: [OSM relation 17060302](https://www.openstreetmap.org/relation/17060302), `natural=water`, `water=reservoir`.
- Both were returned by the same 500 m Overpass water-object search.
- Full geometry contains the sample in South Twin Lake, but not in Wickiup
  Reservoir. The reservoir was rejected for assigning this sample's lake
  metrics; it remains relevant habitat-context evidence.

Later manual review should:

1. Overlay both complete polygons and the sample on suitable imagery/maps.
2. Check whether they touch, share boundary segments, overlap, or are separated;
   record shoreline separation if useful. Neither a shared border nor hydraulic
   connection has been established by the current lookup.
3. Check possible surface connections, seasonal reservoir extent/water levels,
   and whether a mapped separation reflects the real habitat.
4. Check the original sampling description to establish whether the fish were
   collected in open lake water, nearshore/littoral habitat, an inlet/outlet,
   or another habitat. A site name and water polygon alone do not establish this.
5. Record reviewer, date, evidence sources, decision and remaining uncertainty.

Local geometry evidence is retained in
`data/lake_lookup_trials_20261006/S0512/osm_api_way_352410633_polygon.geojson`
and `osm_api_relation_17060302_polygon.geojson` in the same folder.
The original candidate-response cache is
`data/lake_lookup_trials_20261006/nearby_discovery/935dd014f44da00e057215c4.json`.

## Other pending identity checks

- S0485 Blair Lake: the expanded pilot found name-matching way 149828298,
  but its whole polygon does not contain the supplied coordinate
  (45.80386, -64.20407). Inspect shoreline proximity and original sampling
  metadata; the bounded candidate geometry cap also left other nearby objects
  unevaluated. Do not move the coordinate or accept metrics automatically.
- S0391 Rapid Pond: name-matching way 143744492 is tagged `water=pond`, but
  the supplied coordinate (48.9985, -57.692) is outside it. The search also
  returned Humber River and other water objects. Inspect actual habitat and
  original coordinate precision; no pond/lake metrics were accepted.

- S0044: determine what `Mývatn-mud` means in the original sampling metadata;
  do not remove the suffix or equate lake extent with actual sampled habitat.
- S0202: review `Lake Kursinka` against OSM `Курсинка`; transliteration/name
  similarity and containment are evidence, not a certified identity match.
- Review the three pond-name sites in the 40-site selection separately from lakes.

## Logging requirement for the expanded pilot

Retain all returned object types, IDs, tags, discovery stages, search radii,
source timestamps and raw-response references, including candidates excluded
by ranking or classification. The pilot runner appends these records to
`candidate_discovery.jsonl` before requesting geometry, so candidate evidence
survives later geometry-retrieval failure. Empty successful discovery responses
are recorded too. This covers searches actually executed; a successful early
match does not imply an exhaustive inventory of nearby habitat.

Keep geometry retrieval outcomes, rejection reasons and competing polygons
with the evidence. A rejected match must not be interpreted as absence of
ecological influence or connection. Border/connectivity review remains pending.
