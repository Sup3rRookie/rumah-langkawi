# Rumah Langkawi — Japandi house visualiser

A browser-based 3D model of a double-storey house in Langkawi, reconstructed from
the architect's interior floor-layout PDF, used to test a Jotun Japandi paint
scheme under local daylight and to produce a measured paint schedule.

Source drawing dated 06.05.2026. Client and consultant details are withheld, and
the source PDF is not distributed with this repository.

## What this is

**Live:** https://sup3rrookie.github.io/rumah-langkawi/

`dist/rumah-langkawi-3d.html` is a single self-contained file. Open it in any
browser — no server, no build step, no install. It loads three.js from a CDN;
everything else (geometry, palette, logic) is inline. The root `index.html` is
only a redirect, so the GitHub Pages URL lands straight on the app.

The geometry is not hand-authored. It is extracted from the vector linework of
the floor-plan PDF by a set of Python scripts in `scripts/`, which emit JSON into
`data/` and bake the wall geometry directly into the HTML.

## How the extraction works (the important part)

The PDF is plotted **N.T.S.** and every text label is exploded to vector
outlines, so nothing can be read with a text extractor. The method sidesteps
that:

1. **Scale from annotated overall widths.** The plan carries dimension chains.
   Ground-floor overall width is 7640 mm, first floor 8460 mm. Dividing by the
   pixel width of each plan gives two independent scale factors: 34.2478 and
   34.2067 mm/pt. They agree to 0.12%, which proves the underlying CAD geometry
   is internally consistent.
2. **Separate structure from furniture by stroke colour.** Walls are drawn in
   50% grey, furniture in red, dimension lines in black. Filtering on
   `stroking_color` isolates the shell: 182→159 wall faces GF, 222→210 FF after
   cleanup.
3. **Recover doors** from their leaf-plus-swing-arc symbols, compute each hinge
   point, and close the opening so flood-fill room detection works.
4. **Validate against the draughtsman's own dimension chains.** Extracted wall
   coordinates land on annotated chain points (0 / 600 / 2410 / 7640 across;
   660 / 3260 / 4710 / 6990 / 8460 on FF) with 0–10 mm error. This is the
   evidence the reconstruction is real, not fitted.

Verify anytime with `scripts/dims.py` — it re-derives the checks. It needs the
source PDF, which is not in this repository (see below).

## Repo layout

```
data/    extracted JSON (walls, room schedule, paint schedule) + keyplan PNGs
scripts/ Python extraction + build pipeline (see PIPELINE below)
dist/    the built single-file app
src/     EMPTY — target for the Vite/three.js refactor (see HANDOFF.md)
docs/    HANDOFF.md, STATUS.md, this pipeline
```

The source PDF is deliberately excluded — its title block carries client and
consultant names. The extracted JSON in `data/` is the app's input, so the
viewer and the schedules work without it; only the extraction scripts need it.

## Pipeline

Run order, from `scripts/`, with the PDF placed in `data/`:

```
python3 walls.py        # -> data/walls.json     wall centrelines, doors
python3 schedule.py     # -> data/room-schedule.json + keyplan PNGs
python3 paint.py        # -> data/paint-schedule.json
python3 build_app.py    # -> dist/rumah-langkawi-3d.html  (geometry baked in)
```

Dependencies: `pdfplumber`, `numpy`, `scipy`, `Pillow`. The build embeds a ~56 KB
JSON payload of wall and furniture segments into the HTML template.

## App features (current)

- Both floors at true plan dimensions, 4× display scale
- Side-by-side or stacked layout
- Orbit and first-person walk (WASD / arrows)
- Click-to-paint any wall face; shift-click paints a whole floor
- 12-colour Jotun palette
- Daylight scrubber 07:00–19:00 with adjustable north bearing
- Dog-leg staircase reconstructed from the plan's tread lines
- Copy-to-clipboard painter spec

## Known-good numbers

- GF 7640 × 17549 mm, FF 8460 × 17528 mm
- Staircase: |_| dog-leg, landing west, ~290 mm going, 16 risers (assumed)
- Ceiling: 3.0 m both floors (Malaysian standard, ASSUMED — see open items)
- Paint totals at 3.0 m: Timeless 50.9 L, Light clay 29.0 L, Tender greige
  15.9 L, Parchment 13.7 L, primer 54.8 L, ceiling 37.3 L

See `docs/STATUS.md` for what's solid vs assumed, and `docs/HANDOFF.md` for the
next-phase plan.
