# Handoff — for the next session (Cowork)

You're picking up a working single-file prototype and, ideally, turning it into a
maintainable project while resolving the open measurements. Read `README.md` then
`docs/STATUS.md` first. Everything here assumes that context.

## The one thing to get right

The geometry is **real and validated** — do not regenerate it from scratch or
let it drift. It's extracted from the PDF and cross-checked against the
draughtsman's dimension chains to 0–10 mm. If you refactor, preserve
`data/walls.json` as the source of truth and re-validate with `scripts/dims.py`
after any change.

## Highest-leverage next step

Get the **Staircase Elevation PDF** into the workspace. It failed to upload last
session. It unblocks the floor-to-floor height (likely 3135, not the assumed
3000), the flight count (its LEFT/CENTER/RIGHT views suggest three flights, not
the two currently modelled), and the riser count. Measure it the same way the
floor plan was measured: scale from an annotated dimension, extract tread
geometry, derive riser/going. Until then the stair and all vertical dimensions
are assumptions.

## Suggested refactor (optional but recommended)

The prototype bakes geometry into one HTML file via `scripts/build_app.py`
string-templating. That was right for fast iteration; it won't scale. Target:

- **Vite + three.js** (current release, not the r128 CDN pin — you want modern
  colour management and OrbitControls). TypeScript.
- Load `data/walls.json` at runtime instead of baking it in.
- Set renderer output to sRGB and convert palette hexes correctly — colour
  fidelity is the whole point of this tool, and the r128 default washes swatches
  a shade off.
- Keep the app framework-free; a thin control panel is fine if it grows.
- `src/` is empty and waiting for this.

Do not treat the refactor as blocking. A correct stair and confirmed heights
matter more than the build system.

## Backlog, in priority order

1. Ingest the elevation; fix floor-to-floor, flight count, risers.
2. Client maps room names → key-plan numbers; re-cut paint schedule per real use.
3. Add true north; wire window orientation into the daylight model.
4. Solidify walls (thickness from paired centrelines) so thicknesses read true.
5. Per-room colour persistence + export a per-room paint schedule PDF with litres.
6. Wet-area ceiling bulkheads (~2.4 m) in the area calc.

## Product notes to carry into any exported spec

Jotun Majestic True Beauty Matt over Majestic Primer, 2 coats, on dry areas;
True Beauty Sheen in wet areas; trims in Supreme Finish Silky Matt; ceilings
Essence Easy Ceiling. Site: 28-day plaster cure, moisture < 16% before primer,
fungicidal wash on any existing mould — this is a humid coastal site and that
matters more than the colour choice.

## Palette (Jotun Malaysia)

1024 Timeless · 12303 Natural white · 12308 Unbleached · 1625 Soul ·
12306 Tender greige · 11209 Light clay · 1129 Parchment · 1877 Pebblestone ·
10051 Claywood · 8493 Green tea · 1938 Tea leaves · 9925 Fahm.
Hexes in `scripts/build_app.py` are screen approximations — the physical fandeck
is authority. Composition target: ~70% light ground, 20% mid neutral, 10%
dark/green accent, one dark moment per sightline.
