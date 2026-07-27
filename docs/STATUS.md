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
- **Stair geometry, measured.** Read off the plan's nosing lines: flight A
  z 6525–7365, x 4490–6520, 7 treads at 290 mm; a straight half-space landing
  on the 970 mm strip at the EAST end (x 6520–7490); then flight B z 8530–9560
  back along x 6520–4490, 7 treads. 8 risers per flight, 16 floor to floor.
  An earlier pass put the turn on the WEST — that was wrong, the plan's tread
  lines put both flights hard against x 6520 with the turn strip east of them.
- **Stairwell cleanup.** The flight setting-out lines (z 6525 / 7365 / 8530,
  x 6520, and the three turn nosings) were extruding as 3 m walls and boxing the
  stair in. They are now stripped, so the stair reads as an open flight with a
  balustrade. GF wall faces 159 → 152.
- **Stair is modelled as joinery**, not floating slabs: treads with a 25 mm
  nosing, risers, strings to both sides of each flight, newel posts, a pitched
  handrail and balusters around the open well.

## Assumed — needs client confirmation before it's real

- **Ceiling height 3.0 m both floors.** Malaysian standard, chosen because a
  floor layout carries no vertical data. Everything vertical scales off this.
- **Floor-to-floor height.** The uploaded Staircase Elevation text mentions
  **3135**, which is very likely the true floor-to-floor and would replace the
  3000 assumption. Not yet confirmed. Impact: riser 187.5 → ~196 mm, and every
  wall area (hence litre count) shifts ~4.5%.
- **Riser count 16**, now derived rather than guessed: 7 treads per flight plus
  the step onto the landing, twice. At 3.0 m that is a 187.5 mm riser; at 3135
  it is 196 mm, which with the measured 290 mm going puts 2R+G at 682 mm —
  above the ideal 600–660 band but ordinary for a Malaysian domestic stair.
- **Whether the landing is flat.** The plan carries four nosing-spaced lines
  across the landing strip (z 7365/7655/7950/8235/8530 at 290/295/285/295).
  Read literally those are winders, which would make it 19 risers at ~165 mm —
  a notably more comfortable stair. The client's photograph of the built stair
  shows a **straight landing**, so that is what is modelled. Worth resolving
  against the elevation, because it moves the riser by 30 mm.
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
3. **`scripts/dims.py` no longer reproduces the dimension-chain validation.**
   It looks for long black horizontal dimension lines above each plan; this PDF
   has only 14 black horizontal lines over 40 pt in the whole page, none in that
   band, so it reports zero chains. The 0–10 mm figure quoted in the README
   comes from an earlier session and is currently **unverified** — either the
   colour/zone filters need reworking against this file, or the drawing was
   re-exported. Fix this before quoting the figure to anyone.
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
