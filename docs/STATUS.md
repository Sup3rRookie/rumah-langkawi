# Status — what's done, what's assumed, what's open

Last worked: this session. Everything below reflects `dist/rumah-langkawi-3d.html`
as shipped.

## Done and validated (high confidence)

- **Plan-to-metric extraction.** Wall geometry recovered from the PDF vector
  linework. Two independent scale factors agree to 0.12%. Extracted walls land on
  the draughtsman's annotated dimension chains within 0–10 mm. This is checkable
  and reproducible via `scripts/dims.py`.
- **Floor footprints.** GF 7640 × 17549 mm, FF 8460 × 17528 mm.
- **Structure/furniture separation** by stroke colour. Clean.
- **Room schedule** from traced perimeters (not bounding boxes), so irregular
  rooms — the master's front bay, the family area — are measured correctly.
- **3D app** runs offline as a single file; orbit, walk, paint, daylight, floor
  toggles, side-by-side/stacked all functional.
- **Stair footprint and plan orientation.** Located from the 290 mm tread lines
  at x 4490–7490 on the GF; |_| dog-leg, landing to the west (last corrected).
- **Stairwell cleanup.** Tread lines and interior partition lines that were
  extruding as white walls are now stripped; the void is cut into the FF slab.

## Assumed — needs client confirmation before it's real

- **Ceiling height 3.0 m both floors.** Malaysian standard, chosen because a
  floor layout carries no vertical data. Everything vertical scales off this.
- **Floor-to-floor height.** The uploaded Staircase Elevation text mentions
  **3135**, which is very likely the true floor-to-floor and would replace the
  3000 assumption. Not yet confirmed. Impact: riser 187.5 → ~196 mm, and every
  wall area (hence litre count) shifts ~4.5%.
- **Riser count 16.** Assumed to make a comfortable stair. The elevation shows
  LEFT / CENTER / RIGHT — three elevations, which suggests a **three-flight**
  stair with two landings, not the two-flight |_| currently modelled.
- **Room names and colour assignments.** Provisional, inferred from size and
  position. Client has not yet mapped the numbered key-plan spaces to actual uses.
- **Paint spreading rate 12 m²/L.** Working figure for smooth plaster; confirm
  against the Majestic True Beauty datasheet at the dealer. Rough plaster → 9–10,
  which adds ~20%.
- **15% openings deduction.** Blanket figure. GF is heavily glazed and likely
  needs more; wet areas less.

## Open items (ranked by leverage)

1. **Staircase Elevation PDF never reached the sandbox.** Only the floor layout
   uploaded successfully. Re-attach so the stair vertical can be measured instead
   of assumed. This unblocks items 2–4 below. Text seen so far: 3135, 2100, three
   repeats of 993, plus 970/1105/1984/1990/2019/2204/1724/1325/1217/856.
2. **Confirm floor-to-floor height** (3135 vs 3000).
3. **Confirm flight count** (2 vs 3) and riser count. Rebuild stair accordingly.
4. **Map room names** onto the key plan (`keyplan_gf.png`, `keyplan_ff.png`
   regenerate from `scripts/schedule.py`). Then re-cut the paint schedule per
   real use and colour intent.
5. **True north bearing** for the house. Without it the daylight model's
   room-by-room story (which rooms need warmer colours) is on an assumed
   orientation. Take off the site plan or a compass reading at the house.
6. **Ceiling treatment in wet areas** — bulkheads often drop bath ceilings to
   ~2.4 m, which reduces those wall areas.

## Model caveats (by design, not bugs)

- Walls are extruded as thin planes from CAD centrelines — faithful to the
  drawing, but do not read wall *thicknesses* off the model.
- The staircase is code-proportioned to fit the detected footprint and the
  assumed rise. It is not yet a survey of the built stair (see items 1–3).
- Furniture renders as flat outlines on the slab — orientation aid, not a
  furnishing proposal.
