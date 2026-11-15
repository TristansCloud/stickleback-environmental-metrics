# Scientific validation and next steps

Updated 2026-11-14 following the project owner's clarification of the thesis
method. This is a plan; no sensitivity experiment, drainage-buffer extraction
or depth prediction was performed during the documentation update.

## 1. Establish a comparable release

Inventory the original review bundle, selected OSM lookup, MERIT table and
whole-band shoreline table. For each, retain the release ID or input checksum,
site IDs, habitat labels, selected polygon IDs and geometry checksum, method,
units and missingness statuses. Check that a measurement belongs to the polygon
and habitat label shown for the same sample. Preserve old results as history.

Deliverable: one coverage table and a mismatch queue, distinguishing no polygon,
no valid raster cells, unstable water reference, budget limits and an older
measurement that has not been refreshed. Reconcile the differing lake counts
in the [recorded snapshots](current_status.md) before publishing new totals.

## 2. Recover the thesis predictor definitions

The owner confirms that terrain was summarized in a ring around the lake
perimeter. Recover the equation, coefficients, units, ring width, elevation
statistic, water-elevation reference and treatment of island shores from the
thesis. The exact method has not yet been checked against the document.

The current implementation includes island shores in perimeter and terrain
bands. The suggestion that islands imply shallower habitat is plausible working
interpretation supplied by the owner, not an established rule or reason to
change the calculation. Keep geometric description separate from biological
interpretation; a single area/perimeter or terrain statistic need not capture
all relevant habitat structure.

Deliverable: a predictor-to-method mapping stating which existing columns match
the thesis and which would need a separate calculation. No depth equation or
new island policy should be inferred from the clarification alone.

## 3. Assess shoreline geometry sensitivity

Use a geographically varied subset spanning lake size, simple/complex shores,
islands and containing/near-shore matches. Start with the existing raw, 5, 10,
25 and 50 m simplification comparison; inspect area, perimeter, A/P and shoreline
development together with topology and island retention.

`scripts/report_lake_resolution.py` currently expects the pilot GeoJSON and its
companion `lake_polygon_pilot.csv`; it is not a general current-release command.
Its sample-containment rule also rejects near-shore proposals whose original
coordinate is outside the raw polygon. Any future adaptation must distinguish
that existing match status from a new geometry failure, retain original
coordinates and avoid silently moving points to obtain a passing comparison.

The raw geometry remains preserved. The existing 1% area-change limit is an
algorithmic screening rule, not evidence that perimeter is accurate. A common
simplification tolerance cannot restore detail absent from a coarse source.
Select a reporting convention only after examining the comparisons and thesis
calibration requirements. Retain unresolved cases rather than forcing one
tolerance to pass every lake.

Deliverable: sensitivity results and a proposed convention, with exceptions.
If thesis-compatible outer-shore and all-shore variants are needed, label them
separately rather than replacing the current island-inclusive fields.

## 4. Evaluate terrain resolution where it matters

After recovering the ring definition, compare native GLO-90 and GLO-30 on a
small paired subset (approximately 10–20 varied lakes). Hold geometry, ring and
summary definitions constant so the comparison isolates source resolution.
Record native-cell counts, missingness, water-reference stability and changes
in relative elevations, including island-rich and small/narrow lakes.

This is a proposed experiment, not an implemented GLO-30 full-band adapter.
Finer spacing may improve coverage but does not remove vegetation/building
effects from a surface model. Do not resample GLO-90 to claim new information.
Avoid treating a band elevation difference as the thesis slope predictor until
their definitions have been shown to agree.

Deliverable: evidence for retaining GLO-90 or adding a separately versioned
method, rather than an automatic full-dataset rerun.

## 5. Check MERIT maxima before changing their extraction region

Keep the current lake-polygon maximum and 150 m stream-buffer maximum as
explicitly named measurements. The owner reports using the maximum in the
thesis with good agreement to outlet drainage area. Lake maxima describe
modelled drainage context, not discharge or measured lake circulation.

First inspect representative known outlets, flat lakes, near-shore proposals
and stream confluences. A useful future diagnostic is the native maximum-cell
location (with a deterministic rule for ties), its flow direction and distance
to the sample or lake boundary. The current collector stores the maximum and
valid-cell count, but does not retain that location or check connectivity.

Only if these checks indicate missed outlet cells should a small, predefined
outward buffer be evaluated on the same examples. Compare the unbuffered and
buffered maxima and inspect any newly selected cells for downstream tributaries
or unrelated channels. A larger value alone is not proof of improvement.

Deliverable: evidence that the current region is adequate, or a documented
failure mode and justified buffer rule. Do not add a buffer or require a new
drainage collection now. Keep this validation separable from the shoreline work.

## 6. Publish the reconciled review release

After the relevant checks, package the exact table and geometries with coverage,
dictionary, provenance, method versions and the unresolved-review queue. Make
the atlas and downloads identify those same inputs. Verify live file transfers
and stored values separately from display rounding. Habitat/polygon identity
and biological interpretation still require expert review; missing values
remain null. Marine-specific expansion remains deferred.
