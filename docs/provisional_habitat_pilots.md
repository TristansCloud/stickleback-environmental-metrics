# Provisional habitat development sets

These cohorts let stream, marine, and estuary/brackish workflow development
proceed while the input dataset awaits expert review. They are **not a labelled
benchmark** and must not be used to report classification accuracy.

Each class has five core examples (name and ecotype evidence agree under the
existing heuristic) and two challenges (missing, ambiguous, or conflicting name
evidence). All 21 records are unverified and require review, including the core
examples. They retain the original six input columns and stable `sample_id`.
Neither the immutable 599-site source nor the existing 40-lake selection changes.

## Files and reproduction

The files are in [`data/habitat_pilots`](../data/habitat_pilots):

| File | Workflow to develop | Check before accepting measurements |
| --- | --- | --- |
| `stream_pilot_sites_v1.csv` | Channel identity, drainage/network context | Actual channel at sample point; tidal influence; network connectivity and source coverage |
| `marine_pilot_sites_v1.csv` | Coastal/open-water ocean sampling | Point is water; coastal pixel/land contamination; depth and product coverage; whether this was a marine collection location |
| `transition_pilot_sites_v1.csv` | Estuary, lagoon, marsh, mixed-domain handling | Freshwater/marine influence and applicable source domains; avoid forcing one salinity or catchment interpretation |

Install and regenerate offline from the repository root:

```sh
python -m pip install -e ".[test]"
python scripts/prepare_habitat_pilots.py
python -m pytest -q
```

The generator validates the source, assigns mutually exclusive workflow queues,
deduplicates normalized names and exact coordinates, and chooses geographically
spread examples using great-circle distance. Input order does not affect the
result. Ties use `sample_id`. The manifest records the source SHA-256, selection
version, IDs, and output checksums. No geocoding, OSM, DEM, or Earth Engine
request is made. A shortage fails explicitly instead of adding unsupported sites.

## Interpreting the evidence

- `pilot_class` means **workflow queue**, not a new definitive sample label.
  `stream` covers rivers/creeks; `transition` covers candidate estuary/brackish
  contexts without asserting measured salinity.
- `validation_role` separates core from challenge examples. Core means stronger
  agreement between two existing clues, not independent verification.
- `name_inferred_waterbody_type`, `matched_terms`, and
  `name_inference_confidence` are outputs of the existing name heuristic. Its
  `high` confidence means lexical confidence, not measured habitat certainty.
- `working_waterbody_type`, `working_type_basis`, and `manual_review` preserve
  the existing inference. `manual_review=False` does not waive review for these
  sets: every row has `review_required=True` and
  `classification_status=provisional_unverified`.
- Broad ecotype may describe a population's biology rather than the collection
  waterbody. Name/ecotype agreement is therefore supporting evidence only.
- Transition evidence takes precedence over a component river cue. A river name
  paired with marine ecotype is a stream challenge, retaining `working` marine;
  it is not silently changed to freshwater. Unnamed freshwater sites are not
  guessed into rivers. Marine slough/tidal names are challenges even if the
  name heuristic also finds a bay.

For example, Luga River (`S0162`) enters the stream challenge set while retaining
its original marine ecotype. Vaya River mouth (`S0530`) enters the transition
challenge set while retaining freshwater. These are useful ambiguity tests,
not contradictory labels that need to be overwritten to make a pipeline pass.

## What is ready, and what remains

The cohorts and selection tests are ready. Habitat-specific acquisition and
scientific reference values are not supplied by this change. Use these files as
inputs when building the corresponding adapters. The existing lake CLI still
selects its lake-specific cohort; passing a river cohort to it is not a river
pipeline. Do not infer correctness from successful retrieval alone.

For core examples, initially test identity/geometry and applicable-source status.
For challenges, test that uncertainty stays visible and no definitive class,
catchment, or environmental value is invented. Once Marius reviews the samples,
confirmed examples can become a reference validation set. Keep unresolved cases
as challenges; do not train and evaluate a classifier against these same inferred
labels.

## Recording expert review

Ask for the collection waterbody class per `sample_id`: lake, river/stream,
marine, estuary/brackish, or unknown, plus waterbody name and coordinate
corrections where available. The CSVs include blank
`reviewed_waterbody_class`, `reviewer`, and `review_notes` fields. Retain the
original evidence when adding those answers; a reviewed label should be a new
version, not an edit to the immutable input source.

Regeneration refuses to overwrite any cohort with a nonempty review field and
checks all files before writing any. Use `--output-dir` to compare a fresh
selection in a different directory. The initial manifest describes the frozen,
unreviewed selection; if expert review changes a CSV, preserve that initial
manifest and record the reviewed result separately rather than interpreting its
old checksum as current.
